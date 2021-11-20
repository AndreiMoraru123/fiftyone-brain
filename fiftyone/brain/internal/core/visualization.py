"""
Visualization methods.

| Copyright 2017-2021, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import logging

import numpy as np
import sklearn.decomposition as skd
import sklearn.manifold as skm

import eta.core.utils as etau

import fiftyone.core.brain as fob
import fiftyone.core.utils as fou
import fiftyone.core.validation as fov
import fiftyone.zoo as foz

from fiftyone.brain.visualization import (
    VisualizationResults,
    UMAPVisualizationConfig,
    TSNEVisualizationConfig,
    PCAVisualizationConfig,
)
import fiftyone.brain.internal.core.utils as fbu

umap = fou.lazy_import("umap")


logger = logging.getLogger(__name__)


_DEFAULT_MODEL = "mobilenet-v2-imagenet-torch"
_DEFAULT_BATCH_SIZE = None


def compute_visualization(
    samples,
    patches_field,
    embeddings,
    brain_key,
    num_dims,
    method,
    model,
    batch_size,
    force_square,
    alpha,
    skip_failures,
    **kwargs,
):
    """See ``fiftyone/brain/__init__.py``."""

    fov.validate_collection(samples)

    if model is None and embeddings is None:
        model = foz.load_zoo_model(_DEFAULT_MODEL)
        if batch_size is None:
            batch_size = _DEFAULT_BATCH_SIZE

    if etau.is_str(embeddings):
        embeddings_field = embeddings
        embeddings = None
    else:
        embeddings_field = None

    config = _parse_config(
        embeddings_field, model, patches_field, method, num_dims, **kwargs
    )
    brain_method = config.build()

    brain_method.ensure_requirements()

    if brain_key is not None:
        brain_method.register_run(samples, brain_key)

    embeddings = fbu.get_embeddings(
        samples,
        model=model,
        patches_field=patches_field,
        embeddings_field=embeddings_field,
        embeddings=embeddings,
        batch_size=batch_size,
        force_square=force_square,
        alpha=alpha,
        skip_failures=skip_failures,
    )

    logger.info("Generating visualization...")
    points = brain_method.fit(embeddings)

    results = VisualizationResults(samples, config, points)
    brain_method.save_run_results(samples, brain_key, results)

    return results


class Visualization(fob.BrainMethod):
    def fit(self, embeddings):
        raise NotImplementedError("subclass must implement fit()")

    def get_fields(self, samples, brain_key):
        fields = []
        if self.config.patches_field is not None:
            fields.append(self.config.patches_field)

        return fields

    def cleanup(self, samples, brain_key):
        pass


class UMAPVisualization(Visualization):
    def ensure_requirements(self):
        fou.ensure_package(
            "umap-learn",
            error_msg=(
                "You must install the `umap-learn` package in order to use "
                "UMAP-based visualization. This is recommended, as UMAP is "
                "awesome! If you do not wish to install UMAP, try "
                "`method='tsne'` instead"
            ),
        )

    def fit(self, embeddings):
        _umap = umap.UMAP(
            n_components=self.config.num_dims,
            n_neighbors=self.config.num_neighbors,
            metric=self.config.metric,
            min_dist=self.config.min_dist,
            random_state=self.config.seed,
            verbose=self.config.verbose,
        )
        return _umap.fit_transform(embeddings)


class TSNEVisualization(Visualization):
    def fit(self, embeddings):
        if self.config.pca_dims is not None:
            _pca = skd.PCA(
                n_components=self.config.pca_dims,
                svd_solver=self.config.svd_solver,
                random_state=self.config.seed,
            )
            embeddings = _pca.fit_transform(embeddings)

        embeddings = embeddings.astype(np.float32, copy=False)

        verbose = 2 if self.config.verbose else 0

        _tsne = skm.TSNE(
            n_components=self.config.num_dims,
            perplexity=self.config.perplexity,
            learning_rate=self.config.learning_rate,
            metric=self.config.metric,
            init="pca",  # "random" or "pca"
            n_iter=self.config.max_iters,
            random_state=self.config.seed,
            verbose=verbose,
        )
        return _tsne.fit_transform(embeddings)


class PCAVisualization(Visualization):
    def fit(self, embeddings):
        _pca = skd.PCA(
            n_components=self.config.num_dims,
            svd_solver=self.config.svd_solver,
            random_state=self.config.seed,
        )
        return _pca.fit_transform(embeddings)


def _parse_config(
    embeddings_field, model, patches_field, method, num_dims, **kwargs
):
    if method is None or method == "umap":
        config_cls = UMAPVisualizationConfig
    elif method == "tsne":
        config_cls = TSNEVisualizationConfig
    elif method == "pca":
        config_cls = PCAVisualizationConfig
    else:
        raise ValueError("Unsupported method '%s'" % method)

    return config_cls(
        embeddings_field=embeddings_field,
        model=model,
        patches_field=patches_field,
        num_dims=num_dims,
        **kwargs,
    )
