"""
tests/test_diff_analyzer.py

Unit tests for src/analyzers/diff_analyzer.py.
All tests use static diff fixtures — no subprocess / git calls.
"""

import pytest

from src.analyzers.diff_analyzer import (
    ChangeType,
    CodeChange,
    DiffAnalysis,
    DiffAnalyzer,
    _parse_diff,
    _snake_to_camel,
)

# ---------------------------------------------------------------------------
# Fixtures — realistic unified-diff snippets
# ---------------------------------------------------------------------------

MUTATION_DIFF = """\
diff --git a/saleor/graphql/order/mutations/draft_order_create.py b/saleor/graphql/order/mutations/draft_order_create.py
index abc1234..def5678 100644
--- a/saleor/graphql/order/mutations/draft_order_create.py
+++ b/saleor/graphql/order/mutations/draft_order_create.py
@@ -1,10 +1,12 @@
 from graphene import Mutation

-class DraftOrderCreate(BaseMutation):
+class DraftOrderCreate(ModelMutation):
     class Arguments:
         input = DraftOrderCreateInput(required=True)

+class DraftOrderBulkCreate(BaseMutation):
+    pass
"""

RESOLVER_DIFF = """\
diff --git a/saleor/graphql/product/resolvers.py b/saleor/graphql/product/resolvers.py
index 111aaaa..222bbbb 100644
--- a/saleor/graphql/product/resolvers.py
+++ b/saleor/graphql/product/resolvers.py
@@ -5,6 +5,10 @@

-def resolve_products(info, **kwargs):
+def resolve_products(info, channel=None, **kwargs):
     return Product.objects.all()

+def resolve_product_variants(info, **kwargs):
+    return ProductVariant.objects.all()
"""

MODEL_DIFF = """\
diff --git a/saleor/product/models.py b/saleor/product/models.py
index aaa1111..bbb2222 100644
--- a/saleor/product/models.py
+++ b/saleor/product/models.py
@@ -1,5 +1,9 @@
 from django.db import models

 class Product(models.Model):
     name = models.CharField(max_length=255)
+    slug = models.SlugField(unique=True)
+
+class ProductVariant(models.Model):
+    sku = models.CharField(max_length=100)
"""

NEW_FILE_DIFF = """\
diff --git a/saleor/graphql/payment/mutations/payment_refund.py b/saleor/graphql/payment/mutations/payment_refund.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/saleor/graphql/payment/mutations/payment_refund.py
@@ -0,0 +1,5 @@
+from graphene import Mutation
+
+class PaymentRefund(BaseMutation):
+    pass
"""

DELETED_FILE_DIFF = """\
diff --git a/saleor/graphql/order/mutations/old_mutation.py b/saleor/graphql/order/mutations/old_mutation.py
deleted file mode 100644
index abc1234..0000000
--- a/saleor/graphql/order/mutations/old_mutation.py
+++ /dev/null
@@ -1,3 +0,0 @@
-class LegacyMutation(BaseMutation):
-    pass
"""

UNTRACED_DIFF = """\
diff --git a/saleor/core/utils.py b/saleor/core/utils.py
index 111aaaa..222bbbb 100644
--- a/saleor/core/utils.py
+++ b/saleor/core/utils.py
@@ -1,3 +1,4 @@
+import os

 def some_helper():
     pass
"""

COMBINED_DIFF = "\n".join(
    [MUTATION_DIFF, RESOLVER_DIFF, MODEL_DIFF, UNTRACED_DIFF]
)


# ---------------------------------------------------------------------------
# _snake_to_camel
# ---------------------------------------------------------------------------

class TestSnakeToCamel:
    def test_simple_resolver(self):
        assert _snake_to_camel("resolve_products") == "products"

    def test_multi_word(self):
        assert _snake_to_camel("resolve_product_variants") == "productVariants"

    def test_no_resolve_prefix(self):
        assert _snake_to_camel("some_name") == "someName"

    def test_single_word_after_resolve(self):
        assert _snake_to_camel("resolve_orders") == "orders"


# ---------------------------------------------------------------------------
# _parse_diff
# ---------------------------------------------------------------------------

class TestParseDiff:
    def test_mutation_file_detected(self):
        changes = _parse_diff(MUTATION_DIFF)
        assert len(changes) == 1
        c = changes[0]
        assert "mutations/draft_order_create.py" in c.file_path
        assert c.change_type == ChangeType.MODIFIED

    def test_added_lines_captured(self):
        changes = _parse_diff(MUTATION_DIFF)
        added = "\n".join(changes[0].added_lines)
        assert "DraftOrderBulkCreate" in added

    def test_removed_lines_captured(self):
        changes = _parse_diff(MUTATION_DIFF)
        removed = "\n".join(changes[0].removed_lines)
        assert "DraftOrderCreate" in removed

    def test_new_file_change_type(self):
        changes = _parse_diff(NEW_FILE_DIFF)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.ADDED

    def test_deleted_file_change_type(self):
        changes = _parse_diff(DELETED_FILE_DIFF)
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.DELETED

    def test_resolver_file_parsed(self):
        changes = _parse_diff(RESOLVER_DIFF)
        assert len(changes) == 1
        assert "resolvers.py" in changes[0].file_path

    def test_model_file_parsed(self):
        changes = _parse_diff(MODEL_DIFF)
        assert len(changes) == 1
        assert "models.py" in changes[0].file_path

    def test_empty_diff(self):
        assert _parse_diff("") == []

    def test_multiple_files(self):
        changes = _parse_diff(COMBINED_DIFF)
        assert len(changes) == 4


# ---------------------------------------------------------------------------
# DiffAnalyzer.analyze_diff_text — operation mapping
# ---------------------------------------------------------------------------

class TestDiffAnalyzer:
    def setup_method(self):
        self.analyzer = DiffAnalyzer()

    def test_mutation_class_extracted(self):
        result = self.analyzer.analyze_diff_text(MUTATION_DIFF)
        assert "DraftOrderCreate" in result.affected_operations
        assert "DraftOrderBulkCreate" in result.affected_operations

    def test_resolver_name_converted_to_camel(self):
        result = self.analyzer.analyze_diff_text(RESOLVER_DIFF)
        assert "products" in result.affected_operations
        assert "productVariants" in result.affected_operations

    def test_model_types_extracted(self):
        result = self.analyzer.analyze_diff_text(MODEL_DIFF)
        assert "Product" in result.affected_operations
        assert "ProductVariant" in result.affected_operations

    def test_untraced_file_reported(self):
        result = self.analyzer.analyze_diff_text(UNTRACED_DIFF)
        assert any("utils.py" in p for p in result.untraced_changes)

    def test_new_mutation_file_extracted(self):
        result = self.analyzer.analyze_diff_text(NEW_FILE_DIFF)
        assert "PaymentRefund" in result.affected_operations

    def test_deleted_mutation_still_traced(self):
        result = self.analyzer.analyze_diff_text(DELETED_FILE_DIFF)
        assert "LegacyMutation" in result.affected_operations

    def test_no_duplicates_in_affected(self):
        result = self.analyzer.analyze_diff_text(COMBINED_DIFF)
        assert len(result.affected_operations) == len(set(result.affected_operations))

    def test_empty_diff_returns_empty_analysis(self):
        result = self.analyzer.analyze_diff_text("")
        assert result.changed_files == []
        assert result.affected_operations == []
        assert result.untraced_changes == []

    def test_combined_diff_structure(self):
        result = self.analyzer.analyze_diff_text(COMBINED_DIFF)
        assert isinstance(result, DiffAnalysis)
        assert len(result.changed_files) == 4
        assert len(result.affected_operations) > 0
        assert len(result.untraced_changes) == 1

    def test_return_type_is_diff_analysis(self):
        result = self.analyzer.analyze_diff_text(MUTATION_DIFF)
        assert isinstance(result, DiffAnalysis)
        assert all(isinstance(c, CodeChange) for c in result.changed_files)
