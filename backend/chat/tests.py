from django.contrib.auth import get_user_model
from django.test import TestCase

from documents.models import Document
from .models import Conversation
from .views import resolve_document_scope


class ResolveDocumentScopeTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="alice", password="pw")
        self.conversation = Conversation.objects.create(user=self.user)
        self.document = Document.objects.create(
            user=self.user,
            original_filename="Pradyumna_Baral_Resume_2.pdf",
            stored_file="documents/1/Pradyumna_Baral_Resume_2.pdf",
            file_type="pdf",
            file_size=123,
            status=Document.Status.COMPLETED,
        )

    def test_when_conversation_has_no_docs_and_no_selection_it_falls_back_to_user_docs(self):
        class DummyRequest:
            user = self.user

        ids = resolve_document_scope(DummyRequest(), self.conversation, [])

        self.assertEqual(ids, [self.document.id])
