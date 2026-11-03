"""Native lifecycle safety tests. No business transactions are saved."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import frappe
from my_work import api


class TestNativeFlow(unittest.TestCase):
    def doc(self, docstatus=0, permissions=None, **fields):
        values=dict(doctype="Purchase Order",name="PO-TEST",owner="alice",docstatus=docstatus,modified="version-1",**fields)
        doc=MagicMock()
        for key,value in values.items(): setattr(doc,key,value)
        doc.get.side_effect=values.get
        doc.has_permission.side_effect=lambda action: action in (permissions if permissions is not None else {"read","write","submit","cancel"})
        doc.submit.return_value=doc;doc.cancel.return_value=doc
        return doc

    def test_native_actions_respect_permissions_and_docstatus(self):
        with patch.object(api.frappe,"get_meta",return_value=SimpleNamespace(is_submittable=1)):
            self.assertEqual(api._actions(self.doc(),None),["Submit"])
            self.assertEqual(api._actions(self.doc(1),None),["Cancel"])
            self.assertEqual(api._actions(self.doc(2),None),[])
            self.assertEqual(api._actions(self.doc(permissions={"read","submit"}),None),[])
            self.assertEqual(api._actions(self.doc(1,permissions={"read","write"}),None),[])
        with patch.object(api.frappe,"get_meta",return_value=SimpleNamespace(is_submittable=0)):
            self.assertEqual(api._actions(self.doc(),None),[])

    def test_standard_views_separate_cancelled_from_completed(self):
        for status,expected in [(0,{"all","requests","drafts"}),(1,{"all","requests","completed"}),(2,{"all","requests","cancelled"})]:
            views,state,roles,info=api._document_views(self.doc(status),None,True,False,[],False,set())
            self.assertEqual(set(views),expected)
            self.assertEqual(state,["Draft","Submitted","Cancelled"][status])
        self.assertEqual(api._native_views(self.doc(),False,False,["Submit"],set())[0],[])

    def test_default_claim_requires_native_decision_and_keeps_payment_views(self):
        doc=self.doc();doc.doctype="Expense Claim"
        self.assertEqual(api._next_action(doc,None,["Submit"],None),"Select Approval Status → Save → Submit")
        for status,approval,view in [("Unpaid","Approved","waiting"),("Paid","Approved","completed"),("Rejected","Rejected","rejected")]:
            doc=self.doc(1,status=status,approval_status=approval);doc.doctype="Expense Claim"
            views,*_=api._native_views(doc,True,True,["Cancel"],{"status","approval_status"})
            self.assertIn(view,views)
            self.assertNotIn("approvals",views)

    def test_native_mutations_use_document_methods_and_escaped_comment(self):
        for status,action,method in [(0,"Submit","submit"),(1,"Cancel","cancel")]:
            doc=self.doc(status)
            with patch.object(api,"_document",return_value=doc),patch.object(api.frappe,"db",MagicMock()),patch.object(api,"transitions",return_value={"data":[action]}),patch("my_work.claim_tools._workflow",return_value=None),patch.object(api.frappe,"get_meta",return_value=SimpleNamespace(is_submittable=1)),patch.object(api,"apply_workflow") as workflow:
                result=api.act(doc.doctype,doc.name,action,doc.modified,"<test>")
                getattr(doc,method).assert_called_once_with()
                doc.check_permission.assert_any_call(method)
                workflow.assert_not_called()
                self.assertEqual(result["data"]["name"],doc.name)
                self.assertIn("&lt;test&gt;",doc.add_comment.call_args.args[1])
                self.assertEqual(doc.add_comment.call_args.args[0],"Comment")

    def test_native_validation_failure_is_not_swallowed(self):
        doc=self.doc();doc.submit.side_effect=frappe.ValidationError("Native validation")
        with patch.object(api,"_document",return_value=doc),patch.object(api.frappe,"db",MagicMock()),patch.object(api,"transitions",return_value={"data":["Submit"]}),patch("my_work.claim_tools._workflow",return_value=None),patch.object(api,"_native_actions",return_value=["Submit"]):
            with self.assertRaises(frappe.ValidationError): api.act(doc.doctype,doc.name,"Submit",doc.modified)
        doc.add_comment.assert_not_called()

    def test_active_workflow_never_uses_native_shortcut(self):
        doc=self.doc()
        with patch.object(api,"_document",return_value=doc),patch.object(api.frappe,"db",MagicMock()),patch.object(api,"transitions",return_value={"data":["Submit"]}),patch("my_work.claim_tools._workflow",return_value=SimpleNamespace(name="Active")),patch.object(api,"apply_workflow",return_value=doc) as workflow:
            api.act(doc.doctype,doc.name,"Submit",doc.modified)
            workflow.assert_called_once_with(doc.as_json(),"Submit")
        doc.submit.assert_not_called();doc.cancel.assert_not_called()

    def test_sources_exclude_all_active_workflow_types_and_obey_allowlist(self):
        active=SimpleNamespace(name="Expense Claim")
        def query(doctype,**kwargs):
            if doctype=="Workflow": return ["Expense Claim","Hidden Workflow Type"]
            return ["Expense Claim","Hidden Workflow Type","Purchase Order","Sales Order"]
        with patch.object(api,"_workflows",return_value=[(SimpleNamespace(),active)]),patch.object(api.frappe,"get_all",side_effect=query),patch.object(api,"_config",return_value={"enabled_doctypes":["Expense Claim","Purchase Order"]}),patch.object(api.frappe,"has_permission",return_value=True),patch.object(api.frappe,"get_meta",side_effect=lambda name:SimpleNamespace(name=name)):
            sources=list(api._sources())
            self.assertEqual([meta.name for _,meta in sources],["Expense Claim","Purchase Order"])
            self.assertIsNone(sources[1][0])

    def test_personal_candidate_query_uses_trusted_identity(self):
        meta=SimpleNamespace(name="Expense Claim",get_field=lambda name:SimpleNamespace(fieldtype="Link",options="User"))
        with patch.object(api.frappe,"session",SimpleNamespace(user="alice")),patch.object(api,"_config",return_value={}),patch.object(api.frappe,"get_all",return_value=["EMP-A"]):
            filters=api._native_candidate_filters(meta,{"employee","expense_approver"})
            self.assertEqual(filters,[["owner","=","alice"],["employee","in",["EMP-A"]],["expense_approver","=","alice"]])
