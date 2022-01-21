"""
Hardness methods.

| Copyright 2017-2022, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import logging

import numpy as np
from scipy.special import softmax
from scipy.stats import entropy

import fiftyone.core.brain as fob
import fiftyone.core.labels as fol
import fiftyone.core.utils as fou
import fiftyone.core.validation as fov


logger = logging.getLogger(__name__)


_ALLOWED_TYPES = (fol.Classification, fol.Classifications)


def compute_hardness(samples, label_field, hardness_field):
    """See ``fiftyone/brain/__init__.py``."""

    #
    # Algorithm
    #
    # Hardness is computed directly as the entropy of the logits
    #

    fov.validate_collection(samples)
    fov.validate_collection_label_fields(samples, label_field, _ALLOWED_TYPES)

    if samples._is_frame_field(label_field):
        raise ValueError("Hardness does not yet support frame fields")

    config = HardnessConfig(label_field, hardness_field)
    brain_key = hardness_field
    brain_method = config.build()
    brain_method.ensure_requirements()
    brain_method.register_run(samples, brain_key)

    view = samples.select_fields(label_field)
    processing_frames = samples._is_frame_field(label_field)

    logger.info("Computing hardness...")
    for sample in view.iter_samples(progress=True):
        if processing_frames:
            images = sample.frames.values()
        else:
            images = [sample]

        sample_hardness = []
        for image in images:
            label = _get_data(image, label_field)

            if label is not None:
                hardness = entropy(softmax(np.asarray(label.logits)))
            else:
                hardness = None

            if hardness is not None:
                sample_hardness.append(hardness)

            if processing_frames:
                image[hardness_field] = hardness

        if sample_hardness:
            sample[hardness_field] = np.max(sample_hardness)
        else:
            sample[hardness_field] = None

        sample.save()

    brain_method.save_run_results(samples, brain_key, None)

    logger.info("Hardness computation complete")


# @todo move to `fiftyone/brain/hardness.py`
class HardnessConfig(fob.BrainMethodConfig):
    def __init__(self, label_field, hardness_field, **kwargs):
        self.label_field = label_field
        self.hardness_field = hardness_field
        super().__init__(**kwargs)

    @property
    def method(self):
        return "hardness"


class Hardness(fob.BrainMethod):
    def ensure_requirements(self):
        pass

    def get_fields(self, samples, brain_key):
        label_field = self.config.label_field
        hardness_field = self.config.hardness_field

        fields = [label_field, hardness_field]

        if samples._is_frame_field(label_field):
            fields.append(samples._FRAMES_PREFIX + hardness_field)

        return fields

    def cleanup(self, samples, brain_key):
        label_field = self.config.label_field
        hardness_field = self.config.hardness_field

        samples._dataset.delete_sample_fields(hardness_field, error_level=1)

        if samples._is_frame_field(label_field):
            samples._dataset.delete_frame_fields(hardness_field, error_level=1)

    def _validate_run(self, samples, brain_key, existing_info):
        self._validate_fields_match(brain_key, "hardness_field", existing_info)


def _get_data(sample, label_field):
    label = sample[label_field]
    if label is None:
        return None

    if label.logits is None:
        raise ValueError(
            "Sample '%s' field '%s' has no logits" % (sample.id, label_field)
        )

    return label
