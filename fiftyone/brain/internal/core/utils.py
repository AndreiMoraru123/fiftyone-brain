"""
Utilities.

| Copyright 2017-2023, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import itertools
import logging

import numpy as np

import eta.core.utils as etau

import fiftyone.core.labels as fol
import fiftyone.core.patches as fop
import fiftyone.zoo as foz
from fiftyone import ViewField as F


logger = logging.getLogger(__name__)


def get_ids(
    samples,
    patches_field=None,
    data=None,
    data_type="embeddings",
    handle_missing="skip",
):
    if patches_field is None:
        sample_ids = samples.values("id")

        if data is not None and len(sample_ids) != len(data):
            raise ValueError(
                "The number of %s (%d) in these results no longer matches the "
                "number of samples (%d) in the collection. You must "
                "regenerate the results"
                % (data_type, len(data), len(sample_ids))
            )

        return np.array(sample_ids), None

    sample_ids, label_ids = _get_patch_ids(
        samples, patches_field, handle_missing=handle_missing
    )

    if data is not None and len(sample_ids) != len(data):
        raise ValueError(
            "The number of %s (%d) in these results no longer matches the "
            "number of labels (%d) in the '%s' field of the collection. You "
            "must regenerate the results"
            % (data_type, len(data), len(sample_ids), patches_field)
        )

    return np.array(sample_ids), np.array(label_ids)


def filter_ids(
    samples,
    index_sample_ids,
    index_label_ids,
    index_samples=None,
    patches_field=None,
    allow_missing=True,
    warn_missing=False,
):
    _validate_args(samples, None, patches_field)

    if patches_field is None:
        if samples._is_patches:
            sample_ids = np.array(samples.values("sample_id"))
        else:
            sample_ids = np.array(samples.values("id"))

        keep_inds, good_inds, bad_ids = _parse_ids(
            sample_ids,
            index_sample_ids,
            "samples",
            allow_missing,
            warn_missing,
        )

        if bad_ids is not None:
            sample_ids = sample_ids[good_inds]

        return sample_ids, None, keep_inds, good_inds

    sample_ids, label_ids = _get_patch_ids(samples, patches_field)

    keep_inds, good_inds, bad_ids = _parse_ids(
        label_ids,
        index_label_ids,
        "labels",
        allow_missing,
        warn_missing,
    )

    if bad_ids is not None:
        sample_ids = sample_ids[good_inds]
        label_ids = label_ids[good_inds]

    return sample_ids, label_ids, keep_inds, good_inds


def _get_patch_ids(samples, patches_field, handle_missing="skip"):
    if samples._is_patches:
        sample_id_path = "sample_id"
    else:
        sample_id_path = "id"

    label_type, label_id_path = samples._get_label_field_path(
        patches_field, "id"
    )
    is_list_field = issubclass(label_type, fol._LABEL_LIST_FIELDS)

    sample_ids, label_ids = samples.values([sample_id_path, label_id_path])

    if is_list_field:
        _sample_ids = []
        _label_ids = []
        _add_missing = handle_missing == "image"

        for _id, lids in zip(_sample_ids, _label_ids):
            if lids:
                for _lid in lids:
                    _sample_ids.append(_id)
                    _label_ids.append(_lid)
            elif _add_missing:
                _sample_ids.append(_id)
                _label_ids.append(None)

        sample_ids = _sample_ids
        label_ids = _label_ids

    return np.array(sample_ids), np.array(label_ids)


def _parse_ids(ids, index_ids, ftype, allow_missing, warn_missing):
    if np.array_equal(ids, index_ids):
        return None, None, None

    inds_map = {_id: idx for idx, _id in enumerate(index_ids)}

    keep_inds = []
    bad_inds = []
    bad_ids = []
    for _idx, _id in enumerate(ids):
        ind = inds_map.get(_id, None)
        if ind is not None:
            keep_inds.append(ind)
        else:
            bad_inds.append(_idx)
            bad_ids.append(_id)

    num_missing_index = len(index_ids) - len(keep_inds)
    if num_missing_index > 0:
        if not allow_missing:
            raise ValueError(
                "The index contains %d %s that are not present in the "
                "provided collection" % (num_missing_index, ftype)
            )

        if warn_missing:
            logger.warning(
                "Ignoring %d %s from the index that are not present in the "
                "provided collection",
                num_missing_index,
                ftype,
            )

    num_missing_collection = len(bad_ids)
    if num_missing_collection > 0:
        if not allow_missing:
            raise ValueError(
                "The provided collection contains %d %s not present in the "
                "index" % (num_missing_collection, ftype)
            )

        if warn_missing:
            logger.warning(
                "Ignoring %d %s from the provided collection that are not "
                "present in the index",
                num_missing_collection,
                ftype,
            )

        bad_inds = np.array(bad_inds, dtype=np.int64)

        good_inds = np.full(ids.shape, True)
        good_inds[bad_inds] = False
    else:
        good_inds = None
        bad_ids = None

    keep_inds = np.array(keep_inds, dtype=np.int64)

    return keep_inds, good_inds, bad_ids


def filter_values(values, keep_inds, patches_field=None):
    if patches_field:
        _values = list(itertools.chain.from_iterable(values))
    else:
        _values = values

    _values = np.asarray(_values)

    if _values.size == keep_inds.size:
        _values = _values[keep_inds]
    else:
        num_expected = np.count_nonzero(keep_inds)
        if _values.size != num_expected:
            raise ValueError(
                "Expected %d raw values or %d pre-filtered values; found %d "
                "values" % (keep_inds.size, num_expected, values.size)
            )

    # @todo we might need to re-ravel patch values here in the future
    # We currently do not do this because all downstream users of this data
    # will gracefully handle either flat or nested list data

    return _values


def get_values(samples, path_or_expr, ids, patches_field=None):
    _validate_args(samples, path_or_expr, patches_field)
    return samples._get_values_by_id(
        path_or_expr, ids, link_field=patches_field
    )


def parse_embeddings_field(
    samples, embeddings_field, patches_field=None, allow_embedded=True
):
    if not etau.is_str(embeddings_field):
        raise ValueError(
            "Invalid embeddings_field=%s; expected a string field name"
            % embeddings_field
        )

    if patches_field is None:
        _embeddings_field, is_frame_field = samples._handle_frame_field(
            embeddings_field
        )

        if not allow_embedded and "." in _embeddings_field:
            ftype = "frame" if is_frame_field else "sample"
            raise ValueError(
                "Invalid embeddings_field=%s; expected a top-level %s field "
                "name that contains no '.'" % _embeddings_field
            )

        return embeddings_field

    if embeddings_field.startswith(patches_field + "."):
        _, root = samples._get_label_field_path(patches_field) + "."
        if not embeddings_field.startswith(root):
            raise ValueError(
                "Invalid embeddings_field=%s for patches_field=%s"
                % (embeddings_field, patches_field)
            )

        embeddings_field = embeddings_field[len(root) + 1]

    if not allow_embedded and "." in embeddings_field:
        raise ValueError(
            "Invalid embeddings_field=%s for patches_field=%s; expected a "
            "label attribute name that contains no '.'"
            % (embeddings_field, patches_field)
        )

    return embeddings_field


def get_embeddings(
    samples,
    model=None,
    patches_field=None,
    embeddings_field=None,
    embeddings=None,
    force_square=False,
    alpha=None,
    handle_missing="skip",
    agg_fcn=None,
    batch_size=None,
    num_workers=None,
    skip_failures=True,
):
    _samples = samples

    if embeddings is None:
        if model is not None:
            if etau.is_str(model):
                model = foz.load_zoo_model(model)

            if patches_field is not None:
                logger.info("Computing patch embeddings...")
                embeddings = samples.compute_patch_embeddings(
                    model,
                    patches_field,
                    embeddings_field=embeddings_field,
                    force_square=force_square,
                    alpha=alpha,
                    handle_missing=handle_missing,
                    batch_size=batch_size,
                    num_workers=num_workers,
                    skip_failures=skip_failures,
                )
            else:
                logger.info("Computing embeddings...")
                embeddings = samples.compute_embeddings(
                    model,
                    embeddings_field=embeddings_field,
                    batch_size=batch_size,
                    num_workers=num_workers,
                    skip_failures=skip_failures,
                )

        if embeddings_field is not None:
            if patches_field is not None:
                _samples = samples.filter_labels(
                    patches_field, F(embeddings_field) != None
                )
                _embeddings_path = samples._get_label_field_path(
                    patches_field, embeddings_field
                )
            else:
                _samples = samples.match(F(embeddings_field) != None)
                _embeddings_path = embeddings_field

            embeddings = _samples.values(_embeddings_path)

    if embeddings is None:
        raise ValueError(
            "One of `model`, `embeddings_field`, or `embeddings` must be "
            "provided"
        )

    if isinstance(embeddings, dict):
        embeddings = [
            embeddings.get(_id, None) for _id in _samples.values("id")
        ]

    if patches_field is not None:
        if embeddings_field is not None:
            _handle_missing_patch_embeddings(
                embeddings, _samples, patches_field
            )

        if agg_fcn is not None:
            embeddings = np.stack([agg_fcn(e) for e in embeddings])
        else:
            embeddings = np.concatenate(embeddings, axis=0)
    else:
        if embeddings_field is not None:
            _handle_missing_embeddings(embeddings)

        if agg_fcn is not None:
            embeddings = np.stack([agg_fcn(e) for e in embeddings])
        else:
            embeddings = np.stack(embeddings)

    if agg_fcn is not None:
        patches_field = None

    sample_ids, label_ids = get_ids(
        _samples,
        patches_field=patches_field,
        data=embeddings,
        data_type="embeddings",
        handle_missing=handle_missing,
    )

    return embeddings, sample_ids, label_ids


def _validate_args(samples, path_or_expr, patches_field):
    if patches_field is not None:
        _validate_patches_args(samples, path_or_expr, patches_field)
    else:
        _validate_samples_args(samples, path_or_expr)


def _validate_samples_args(samples, path_or_expr):
    if not etau.is_str(path_or_expr):
        return

    path, _, list_fields, _, _ = samples._parse_field_name(path_or_expr)

    if list_fields:
        raise ValueError(
            "Values path '%s' contains invalid list field '%s'"
            % (path, list_fields[0])
        )


def _validate_patches_args(samples, path_or_expr, patches_field):
    if etau.is_str(path_or_expr) and not path_or_expr.startswith(
        patches_field + "."
    ):
        raise ValueError(
            "Values path '%s' must start with patches field '%s'"
            % (path_or_expr, patches_field)
        )

    if (
        isinstance(samples, fop.PatchesView)
        and patches_field != samples.patches_field
    ):
        raise ValueError(
            "This patches view contains labels from field '%s', not "
            "'%s'" % (samples.patches_field, patches_field)
        )

    if isinstance(
        samples, fop.EvaluationPatchesView
    ) and patches_field not in (
        samples.gt_field,
        samples.pred_field,
    ):
        raise ValueError(
            "This evaluation patches view contains patches from "
            "fields '%s' and '%s', not '%s'"
            % (samples.gt_field, samples.pred_field, patches_field)
        )


def _handle_missing_embeddings(embeddings):
    if isinstance(embeddings, np.ndarray):
        return

    missing_inds = []
    num_dims = None
    for idx, embedding in enumerate(embeddings):
        if embedding is None:
            missing_inds.append(idx)
        elif num_dims is None:
            num_dims = embedding.size

    if not missing_inds:
        return

    missing_embedding = np.zeros(num_dims or 16)
    for idx in missing_inds:
        embeddings[idx] = missing_embedding.copy()

    logger.warning("Using zeros for %d missing embeddings", len(missing_inds))


def _handle_missing_patch_embeddings(embeddings, samples, patches_field):
    missing_inds = []
    num_dims = None
    for idx, embedding in enumerate(embeddings):
        if embedding is None:
            missing_inds.append(idx)
        elif num_dims is None:
            num_dims = embedding.shape[1]

    if not missing_inds:
        return

    missing_embedding = np.zeros(num_dims or 16)

    _, labels_path = samples._get_label_field_path(patches_field)
    patch_counts = samples.values(F(labels_path).length())

    num_missing = 0
    for idx in missing_inds:
        count = patch_counts[idx]
        embeddings[idx] = np.tile(missing_embedding, (count, 1))
        num_missing += count

    if num_missing > 0:
        logger.warning(
            "Using zeros for %d missing patch embeddings", num_missing
        )
