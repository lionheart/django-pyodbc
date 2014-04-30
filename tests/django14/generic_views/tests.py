from __future__ import absolute_import

from .base import ViewTest, TemplateViewTest, RedirectViewTest
from .dates import (ArchiveIndexViewTests, YearArchiveViewTests,
    MonthArchiveViewTests, WeekArchiveViewTests, DayArchiveViewTests,
    DateDetailViewTests)
from .detail import DetailViewTest
from .edit import (FormMixinTests, ModelFormMixinTests, CreateViewTests,
    UpdateViewTests, DeleteViewTests)
from .list import ListViewTests
