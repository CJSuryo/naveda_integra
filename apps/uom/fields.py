"""Reusable form fields for the uom app."""
import itertools
from functools import partial

from django.forms.models import ModelChoiceField, ModelChoiceIterator


class GroupedModelChoiceIterator(ModelChoiceIterator):
    def __init__(self, field, groupby):
        self.groupby = groupby
        super().__init__(field)

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ('', self.field.empty_label)
        for group, objs in itertools.groupby(self.queryset, self.groupby):
            yield (group, [self.choice(obj) for obj in objs])


class GroupedModelChoiceField(ModelChoiceField):
    """A ModelChoiceField that renders <optgroup> elements.

    ``choices_groupby`` receives a model instance and returns its group
    label. The queryset must already be sorted so instances sharing a group
    are contiguous — itertools.groupby only groups consecutive items.
    """
    def __init__(self, *args, choices_groupby, **kwargs):
        self.iterator = partial(GroupedModelChoiceIterator, groupby=choices_groupby)
        super().__init__(*args, **kwargs)
