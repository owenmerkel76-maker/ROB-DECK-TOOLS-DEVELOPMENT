"""Test rollback-control logic with a stub; not a Revit transaction test."""
import ast
import copy
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from rt_layout import validate_deletion_scope


class FakeTransaction:
    def __init__(self, doc, title):
        self.doc, self.status = doc, 'Uninitialized'

    def Start(self):
        self.snapshot = copy.deepcopy(self.doc.state)
        self.status = 'Started'
        return self.status

    def GetFailureHandlingOptions(self):
        return self

    def SetFailuresPreprocessor(self, handler):
        pass

    def SetClearAfterRollback(self, value):
        pass

    def SetFailureHandlingOptions(self, value):
        pass

    def Commit(self):
        if self.doc.reject:
            self.RollBack()
        else:
            self.status = 'Committed'
        return self.status

    def RollBack(self):
        self.doc.state = self.snapshot
        self.status = 'RolledBack'

    def GetStatus(self):
        return self.status

    def Dispose(self):
        pass


class TransactionControlTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / 'lib' / 'rt_revit.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'transaction')
        db = SimpleNamespace(Transaction=FakeTransaction,
                             TransactionStatus=SimpleNamespace(Started='Started', Committed='Committed'))
        scope = dict(DB=db, contextmanager=contextmanager, FailureLogger=lambda log: None)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<transaction-control>', 'exec'), scope)
        self.transaction = scope['transaction']
        self.doc = SimpleNamespace(state={'old_board': 1, 'old_registry': 'old', 'manual_beam': 7}, reject=False)

    def test_dependency_failure_restores_original_layout_and_unrelated_element(self):
        original = copy.deepcopy(self.doc.state)
        with self.assertRaises(ValueError):
            with self.transaction(self.doc, 'rebuild', lambda message: None):
                self.doc.state['new_board'] = 2
                del self.doc.state['old_board']
                del self.doc.state['manual_beam']
                self.doc.state['old_registry'] = 'new'
                validate_deletion_scope({1}, {1, 7})
        self.assertEqual(self.doc.state, original)

    def test_commit_rejection_restores_old_registry(self):
        original = copy.deepcopy(self.doc.state)
        self.doc.reject = True
        with self.assertRaises(RuntimeError):
            with self.transaction(self.doc, 'rebuild', lambda message: None):
                self.doc.state['old_registry'] = 'new'
                self.doc.state['new_board'] = 2
        self.assertEqual(self.doc.state, original)

    def test_success_preserves_unrelated_element(self):
        with self.transaction(self.doc, 'rebuild', lambda message: None):
            del self.doc.state['old_board']
            self.doc.state['new_board'] = 2
            self.doc.state['old_registry'] = 'new'
        self.assertEqual(self.doc.state, {'new_board': 2, 'old_registry': 'new', 'manual_beam': 7})


if __name__ == '__main__':
    unittest.main()
