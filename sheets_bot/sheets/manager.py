"""SheetsManager — assembles the focused mixins into one Sheets facade."""

from __future__ import annotations

from .base import SheetsBase
from .create import CreateMixin
from .ensure import EnsureMixin
from .gviz import GvizMixin
from .headers import HeaderMixin
from .import_row import ImportRowMixin
from .layout import LayoutMixin
from .lookups import LookupMixin
from .products import ProductMixin
from .styling import StyleMixin
from .topic_row import TopicRowMixin
from .writes import WriteMixin


class SheetsManager(
    HeaderMixin,
    StyleMixin,
    LayoutMixin,
    LookupMixin,
    EnsureMixin,
    CreateMixin,
    WriteMixin,
    GvizMixin,
    ProductMixin,
    ImportRowMixin,
    TopicRowMixin,
    SheetsBase,
):
    pass
