import json
import logging
from django.http import StreamingHttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from documents.models import Document
from documents.ai_client import ask_question, stream_answer
from .models import Conversation, ConversationDocument, Message
from .serializers import ConversationSerializer, MessageSerializer, AskQuestionSerializer

logger = logging.getLogger(__name__)

# How many previous messages we send as conversation memory. Simple and
# cheap for MVP — see README/notes for why we don't summarize yet.
HISTORY_LIMIT = 10

DEFAULT_TITLE = "New conversation"
TITLE_MAX_LENGTH = 50


def resolve_document_scope(request, conversation, requested_document_ids=None):
    """
    Return the IDs that the ask-question endpoint should send to the AI service.

    UX contract in the dashboard says "None selected = search all documents".
    The previous implementation accidentally treated an empty selection as
    "search the conversation attachment set," which is usually empty. This
    helper makes the server match the UI contract and the user expectation.
    """
    requested_document_ids = requested_document_ids or []

    # Explicit selection: attach only those owned documents to the conversation
    # and scope retrieval to exactly that list.
    if requested_document_ids:
        owned_ids = list(
            Document.objects.filter(user=request.user, id__in=requested_document_ids)
            .values_list("id", flat=True)
        )
        for doc_id in owned_ids:
            ConversationDocument.objects.get_or_create(conversation=conversation, document_id=doc_id)
        return owned_ids

    # Empty selection means "search all documents this user owns"
    return list(Document.objects.filter(user=request.user).values_list("id", flat=True))


def auto_title_from_question(question: str) -> str:
    """Turns the first question in a conversation into a short title,
    e.g. 'What are the technical skills mentioned...' — trimmed to a
    sensible length so it fits in the sidebar."""
    title = " ".join(question.strip().split())  # collapse whitespace/newlines
    if len(title) > TITLE_MAX_LENGTH:
        title = title[:TITLE_MAX_LENGTH].rsplit(" ", 1)[0] + "..."
    return title or DEFAULT_TITLE


class ConversationListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ConversationDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
        return Response(ConversationSerializer(conversation).data)

    def patch(self, request, pk):
        """Lets the user rename a conversation manually."""
        conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
        serializer = ConversationSerializer(conversation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageListView(generics.ListAPIView):
    """List all messages in a conversation the user owns."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self):
        conversation = get_object_or_404(Conversation, pk=self.kwargs["pk"], user=self.request.user)
        return conversation.messages.all()


def _prepare_question(request, pk, data):
    """
    Shared setup used by both the streaming and non-streaming ask
    endpoints: validate input, resolve document scope, save the user's
    message, auto-title the conversation, and build trimmed history.
    Returns (conversation, question, document_ids, mode, history).
    """
    conversation = get_object_or_404(Conversation, pk=pk, user=request.user)

    serializer = AskQuestionSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    question = serializer.validated_data["question"]
    requested_document_ids = serializer.validated_data["document_ids"]
    mode = serializer.validated_data["mode"]

    document_ids = resolve_document_scope(request, conversation, requested_document_ids)

    is_first_message = not conversation.messages.exists()
    Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)

    if is_first_message and conversation.title == DEFAULT_TITLE:
        conversation.title = auto_title_from_question(question)
        conversation.save(update_fields=["title"])

    history = [
        {"role": m.role, "content": m.content}
        for m in conversation.messages.order_by("-created_at")[:HISTORY_LIMIT][::-1]
    ]

    return conversation, question, document_ids, mode, history


class AskQuestionView(APIView):
    """
    Non-streaming version of the RAG endpoint — kept for any client that
    doesn't need streaming. The chat UI itself uses AskQuestionStreamView.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        conversation, question, document_ids, mode, history = _prepare_question(request, pk, request.data)

        try:
            result = ask_question(
                user_id=request.user.id,
                conversation_id=conversation.id,
                question=question,
                document_ids=document_ids,
                history=history,
                mode=mode,
            )
            answer = result.get("answer", "")
            sources = result.get("sources", [])
        except Exception:
            logger.exception("ask_question() failed for conversation %s", conversation.id)
            answer = "Sorry, something went wrong while generating an answer. Please try again."
            sources = []

        assistant_message = Message.objects.create(
            conversation=conversation, role=Message.Role.ASSISTANT, content=answer, sources=sources
        )
        conversation.save(update_fields=["updated_at"])

        return Response(MessageSerializer(assistant_message).data, status=status.HTTP_201_CREATED)


class AskQuestionStreamView(APIView):
    """
    Streaming version of the RAG endpoint. Proxies Server-Sent Events
    straight from the AI service to the browser, while accumulating the
    full answer text + sources as they stream past — once the stream
    finishes, the complete assistant Message is saved to the database,
    exactly as if it had been generated all at once.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        conversation, question, document_ids, mode, history = _prepare_question(request, pk, request.data)
        user_id = request.user.id

        def event_stream():
            full_answer = ""
            sources = []
            had_error = False
            try:
                for line in stream_answer(
                    user_id=user_id,
                    conversation_id=conversation.id,
                    question=question,
                    document_ids=document_ids,
                    history=history,
                    mode=mode,
                ):
                    yield f"{line}\n\n"
                    if not line.startswith("data:"):
                        continue
                    try:
                        payload = json.loads(line[len("data:"):].strip())
                    except (ValueError, json.JSONDecodeError):
                        continue
                    event_type = payload.get("type")
                    if event_type == "sources":
                        sources = payload.get("sources", [])
                    elif event_type == "chunk":
                        full_answer += payload.get("content", "")
                    elif event_type == "error":
                        had_error = True
            except Exception:
                logger.exception("stream_answer() failed for conversation %s", conversation.id)
                had_error = True
                yield f"data: {json.dumps({'type': 'error', 'detail': 'Something went wrong.'})}\n\n"

            if had_error and not full_answer:
                full_answer = "Sorry, something went wrong while generating an answer. Please try again."

            Message.objects.create(
                conversation=conversation, role=Message.Role.ASSISTANT, content=full_answer, sources=sources
            )
            conversation.save(update_fields=["updated_at"])

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # disables proxy buffering (e.g. nginx) so chunks arrive immediately
        return response
