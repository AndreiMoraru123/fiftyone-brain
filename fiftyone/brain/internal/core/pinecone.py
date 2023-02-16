"""
Piencone similarity backend.

| Copyright 2017-2023, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import logging

import numpy as np

import fiftyone.core.utils as fou

from fiftyone.brain.similarity import (
    SimilarityConfig,
    Similarity,
    SimilarityResults,
)
import fiftyone.brain.internal.core.utils as fbu

pinecone = fou.lazy_import(
    "pinecone", callback=lambda: fou.ensure_package("pinecone")
)


logger = logging.getLogger(__name__)


class PineconeSimilarityConfig(SimilarityConfig):
    """Configuration for the pinecone similarity backend.

    Args:
        embeddings_field (None): the sample field containing the embeddings,
            if one was provided
        model (None): the :class:`fiftyone.core.models.Model` or class name of
            the model that was used to compute embeddings, if one was provided
        patches_field (None): the sample field defining the patches being
            analyzed, if any
        supports_prompts (False): whether this run supports prompt queries
        metric ("euclidean"): the embedding distance metric to use. Supported
            values are "euclidean", "cosine", and "dotproduct".
    """

    def __init__(
        self,
        embeddings_field=None,
        model=None,
        patches_field=None,
        supports_prompts=None,
        metric="euclidean",
        index_name="testname",
        dimension=None,
        pod_type="p1",
        pods=1,
        replicas=1,
        api_key=None,
        environment=None,
        upsert_pagination=100,
        **kwargs,
    ):
        super().__init__(
            embeddings_field=embeddings_field,
            model=model,
            patches_field=patches_field,
            supports_prompts=supports_prompts,
            **kwargs,
        )
        self.metric = metric
        self.index_name = index_name
        self.dimension = dimension
        self.pod_type = pod_type
        self.pods = pods
        self.replicas = replicas
        self.api_key = api_key
        self.environment = environment
        self.upsert_pagination = upsert_pagination

    @property
    def method(self):
        return "pinecone"

    @property
    def supports_least_similarity(self):
        return False

    @property
    def supports_aggregate_queries(self):
        return False

    @property
    def max_k(self):
        return 10000


class PineconeSimilarity(Similarity):
    """Pinecone similarity class for similarity backends.

    Args:
        config: an :class:`PineconeSimilarityConfig`
    """

    def ensure_requirements(self):
        ## do I need "pinecone" here?
        pass

    def initialize(self, samples):
        return PineconeSimilarityResults(samples, self.config, backend=self)

    def cleanup(self, samples, brain_key):
        pass


class PineconeSimilarityResults(SimilarityResults):
    """Class for interacting with pinecone similarity results.

    Args:
        samples: the :class:`fiftyone.core.collections.SampleCollection` used
        config: the :class:`SimilarityConfig` used
        embeddings (None): a ``num_embeddings x num_dims`` array of embeddings
        sample_ids (None): a ``num_embeddings`` array of sample IDs
        label_ids (None): a ``num_embeddings`` array of label IDs, if
            applicable
        backend (None): a :class:`PineconeSimilarity` instance
    """

    def __init__(
        self,
        samples,
        config,
        embeddings=None,
        sample_ids=None,
        label_ids=None,
        backend=None,
    ):
        embeddings, sample_ids, label_ids = self._parse_data(
            samples,
            config,
            embeddings=embeddings,
            sample_ids=sample_ids,
            label_ids=label_ids,
        )

        dimension = self._parse_dimension(embeddings, config)

        self._embeddings = embeddings
        self._dimension = dimension
        self._sample_ids = sample_ids
        self._label_ids = label_ids
        self._index_name = config.index_name
        self._pod_type = config.pod_type
        self._pods = config.pods
        self._replicas = config.replicas
        self._metric = config.metric
        self._upsert_pagination = config.upsert_pagination
        self._api_key = config.api_key
        self._environment = config.environment

        print("Initializing pinecone index")
        pinecone.init(config.api_key, config.environment)
        if self._index_name not in pinecone.list_indexes():
            print("Creating pinecone index")
            pinecone.create_index(
                self._index_name,
                dimension=self._dimension,
                metric=self._metric,
                pod_type=self._pod_type,
                pods=self._pods,
                replicas=self._replicas,
            )

        self._neighbors_helper = None

        super().__init__(samples, config, backend=backend)

    @property
    def sample_ids(self):
        """The sample IDs of the full index."""
        return self._sample_ids

    @property
    def label_ids(self):
        """The label IDs of the full index, or ``None`` if not applicable."""
        return self._label_ids

    def remove_from_index(
        self,
        sample_ids=None,
        label_ids=None,
        allow_missing=True,
        warn_missing=False,
    ):

        pinecone.init(
            api_key=self._api_key,
            environment=self._environment,
        )
        index = pinecone.Index(self._index_name)

        if self._label_ids is not None:
            self._label_ids = [
                lid for lid in self._label_ids if lid not in label_ids
            ]
            index.delete(ids=label_ids)
        elif self._sample_ids is not None:
            self._sample_ids = [
                sid for sid in self._sample_ids if sid not in sample_ids
            ]
            index.delete(ids=sample_ids)

    def _sort_by_similarity(
        self, query, k, reverse, aggregation, return_dists
    ):
        if reverse == True:
            raise ValueError(
                "Pinecone backend does not support reverse sorting"
            )

        if k is None:
            raise ValueError(
                "k must be provided when using pinecone similarity"
            )

        if k > 10000:
            raise ValueError(
                "k cannot be greater than 10000 when using pinecone similarity"
            )

        if query is None:
            raise ValueError(
                "A query must be provided when using aggregate similarity"
            )

        if aggregation is not None:
            raise ValueError("Pinecone backend does not support aggregation")

        sample_ids = self.current_sample_ids
        label_ids = self.current_label_ids

        pinecone.init(
            api_key=self._api_key,
            environment=self._environment,
        )
        index = pinecone.Index(self._index_name)

        if isinstance(query, np.ndarray):
            # Query by vectors
            query_embedding = query.tolist()
        else:
            query_id = query
            query_embedding = index.fetch([query_id])["vectors"][query_id][
                "values"
            ]

        if label_ids is not None:
            response = index.query(
                vector=query_embedding,
                top_k=k,
                filter={"id": {"$in": label_ids}},
            )
        else:
            response = index.query(
                vector=query_embedding,
                top_k=min(k, 10000),
                filter={"id": {"$in": sample_ids}},
            )

        print(response)

        ids = ["63ed9a7ba4c597b4abcc6711" "63ed9a7ba4c597b4abcc6717"]

        if return_dists:
            dists = []
            return ids, dists
        else:
            return ids

    def add_to_index(
        self,
        embeddings,
        sample_ids,
        label_ids=None,
        overwrite=True,
        allow_existing=True,
        warn_existing=False,
    ):

        embeddings_list = [arr.tolist() for arr in embeddings]
        if label_ids is not None:
            id_dicts = [
                {"id": lid, "sample_id": sid}
                for lid, sid in zip(label_ids, sample_ids)
            ]
            index_vectors = list(zip(label_ids, embeddings_list, id_dicts))
        else:
            id_dicts = [{"id": sid, "sample_id": sid} for sid in sample_ids]
            index_vectors = list(zip(sample_ids, embeddings_list, id_dicts))

        num_vectors = embeddings.shape[0]
        num_steps = int(np.ceil(num_vectors / self._upsert_pagination))

        pinecone.init(
            api_key=self._api_key,
            environment=self._environment,
        )
        index = pinecone.Index(self._index_name)

        for i in range(num_steps):
            min_ind = self._upsert_pagination * i
            max_ind = min(self._upsert_pagination * (i + 1), num_vectors)
            index.upsert(index_vectors[min_ind:max_ind])

    def attributes(self):
        attrs = super().attributes()

        if self.config.embeddings_field is not None:
            attrs = [
                attr
                for attr in attrs
                if attr not in ("embeddings", "sample_ids", "label_ids")
            ]

        return attrs

    def _parse_dimension(self, embeddings, config):
        if config.dimension is not None:
            return int(config.dimension)
        elif embeddings is not None:
            return int(embeddings.shape[1])
        return 0

    # def _reload(self, hard=False):
    #     if hard:
    #         # @todo reload embeddings from gridFS too?
    #         # @todo `_samples` is not not declared in SimilarityResults API
    #         if self.config.embeddings_field is not None:
    #             embeddings, sample_ids, label_ids = self._parse_data(
    #                 self._samples,
    #                 self.config,
    #             )

    #             self._embeddings = embeddings
    #             self._sample_ids = sample_ids
    #             self._label_ids = label_ids
    #             self._neighbors_helper = None

    #     self.use_view(self._curr_view)

    def _radius_neighbors(self, query=None, thresh=None, return_dists=False):
        pass

    def _kneighbors(
        self,
        query=None,
        k=None,
        reverse=False,
        keep_ids=None,
        aggregation=None,
        return_dists=False,
    ):
        pass

    def _to_inds(self, ids):
        pass

    def _ensure_neighbors(self):
        pass

    def _get_neighbors(self, full=False):
        pass

    @staticmethod
    def _parse_data(
        samples,
        config,
        embeddings=None,
        sample_ids=None,
        label_ids=None,
    ):
        if embeddings is None:
            embeddings, sample_ids, label_ids = fbu.get_embeddings(
                samples._dataset,
                patches_field=config.patches_field,
                embeddings_field=config.embeddings_field,
            )
        elif sample_ids is None:
            sample_ids, label_ids = fbu.get_ids(
                samples,
                patches_field=config.patches_field,
                data=embeddings,
                data_type="embeddings",
            )

        return embeddings, sample_ids, label_ids

    @classmethod
    def _from_dict(cls, d, samples, config):
        embeddings = d.get("embeddings", None)
        if embeddings is not None:
            embeddings = np.array(embeddings)

        sample_ids = d.get("sample_ids", None)
        if sample_ids is not None:
            sample_ids = np.array(sample_ids)

        label_ids = d.get("label_ids", None)
        if label_ids is not None:
            label_ids = np.array(label_ids)

        config_attrs = [
            "index_name",
            "pod_type",
            "pods",
            "replicas",
            "metric",
            "upsert_pagination",
            "api_key",
            "environment",
        ]

        for attr in config_attrs:
            if attr in d:
                value = d.get("index_name", None)
                if value is not None:
                    config[attr] = value

        return cls(
            samples,
            config,
            embeddings=embeddings,
            sample_ids=sample_ids,
            label_ids=label_ids,
        )
