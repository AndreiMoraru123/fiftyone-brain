"""
Duplicates interface.

| Copyright 2017-2021, Voxel51, Inc.
| `voxel51.com <https://voxel51.com/>`_
|
"""
import numpy as np

import eta.core.utils as etau

import fiftyone.core.brain as fob
import fiftyone.core.utils as fou

fbd = fou.lazy_import("fiftyone.brain.internal.core.duplicates")


class DuplicatesResults(fob.BrainResults):
    """Class storing the results of :meth:`fiftyone.brain.compute_duplicates`.

    Args:
        samples: the :class:`fiftyone.core.collections.SampleCollection` used
        embeddings: a ``num_embeddings x num_dims`` array of embeddings
        config: the :class:`DuplicatesConfig` used
    """

    def __init__(self, samples, embeddings, config):
        self._samples = samples
        self.embeddings = embeddings
        self.config = config

        self.thresh = None
        self.unique_ids = None
        self.dup_ids = None
        self.nearest_ids = None

        self._neighbors = None
        self._visualization = None

    def find_duplicates(self, thresh=None, fraction=None):
        """Queries the index to find duplicate examples based on the provided
        parameters.

        Calling this method populates the :attr:`unique_ids`, :attr:`dup_ids`,
        :attr:`nearest_ids`, and :attr:`thresh` attributes of this object with
        the results of the query.

        Use :meth:`plot_distances`, :meth:`duplicates_view`, and
        :meth:`visualize` to analyze the results generated by this method.

        Args:
            thresh (None): a distance threshold to use to determine duplicates
            fraction (None): a desired fraction of images/patches to tag as
                duplicates, in ``[0, 1]``. If provided, ``thresh`` is
                automatically tuned to achieve the desired fraction of
                duplicates
        """
        return fbd.find_duplicates(self, thresh, fraction)

    def find_unique(self, count):
        """Queries the index to select a subset of examples of the specified
        size that are maximally unique with respect to each other.

        Calling this method populates the :attr:`unique_ids`, :attr:`dup_ids`,
        :attr:`nearest_ids`, and :attr:`thresh` attributes of this object with
        the results of the query.

        Args:
            count: the desired number of unique examples
        """
        return fbd.find_unique(self, count)

    def plot_distances(self, bins=100, log=False, backend="plotly", **kwargs):
        """Plots a histogram of the distance between each example and its
        nearest neighbor.

        If `:meth:`find_duplicates` or :meth:`find_unique` has been executed,
        the threshold used is also indicated on the plot.

        Args:
            bins (100): the number of bins to use
            log (False): whether to use a log scale y-axis
            backend ("plotly"): the plotting backend to use. Supported values
                are ``("plotly", "matplotlib")``
            **kwargs: keyword arguments for the backend plotting method

        Returns:
            one of the following:

            -   a :class:`fiftyone.core.plots.plotly.PlotlyNotebookPlot`, if
                you are working in a notebook context and the plotly backend is
                used
            -   a plotly or matplotlib figure, otherwise
        """
        return fbd.plot_distances(self, bins, log, backend, **kwargs)

    def duplicates_view(self, field):
        """Returns a view that contains only the duplicate examples and their
        corresponding nearest non-duplicate examples generated by the last call
        to :meth:`find_duplicates`.

        If you are analyzing patches, the returned view will be a
        :class:`fiftyone.core.patches.PatchesView`.

        The examples are organized so that each non-duplicate is immediately
        followed by all duplicate(s) that are nearest to it.

        The specified ``field`` will also be populated with "nearest" for each
        non-duplicate and "duplicate" for each duplicate.

        Args:
            field: the name of a field in which to store "nearest" and
                "duplicate" labels

        Returns:
            a :class:`fiftyone.core.view.DatasetView`
        """
        if self.nearest_ids is None:
            raise ValueError(
                "You must first call `find_duplicates()` to generate results"
            )

        return fbd.duplicates_view(self, field)

    def unique_view(self):
        """Returns a view that contains only the unique examples generated by
        the last call to :meth:`find_duplicates` or :meth:`find_unique`.

        If you are analyzing patches, the returned view will be a
        :class:`fiftyone.core.patches.PatchesView`.

        Returns:
            a :class:`fiftyone.core.view.DatasetView`
        """
        if self.unique_ids is None:
            raise ValueError(
                "You must first call `find_unique()` or `find_duplicates()` "
                "to generate results"
            )

        return fbd.unique_view(self)

    def visualize_duplicates(
        self, visualization=None, backend="plotly", **kwargs
    ):
        """Generates an interactive scatterplot of the results generated by the
        last call to :meth:`find_duplicates`.

        If the ``visualization`` argument is not provided and the embeddings
        have more than 3 dimensions, a 2D representation of the points is
        computed via :meth:`fiftyone.brain.compute_visualization`. In either
        case, the visualization used is cached on this object for subsequent
        use during the current session.

        The points are colored based on the following partition:

            -   "duplicate": duplicate example
            -   "nearest": nearest neighbor of a duplicate example
            -   "unique": the remaining unique examples

        Edges are also drawn between each duplicate and its nearest
        non-duplicate neighbor.

        You can attach plots generated by this method to an App session via its
        :attr:`fiftyone.core.session.Session.plots` attribute, which will
        automatically sync the session's view with the currently selected
        points in the plot.

        Args:
            visualization (None): a
                :class:`fiftyone.brain.visualization.VisualizationResults`
                instance to use to visualize the results
            backend ("plotly"): the plotting backend to use. Supported values
                are ``("plotly", "matplotlib")``
            **kwargs: keyword arguments for the backend plotting method:

                -   "plotly" backend: :meth:`fiftyone.core.plots.plotly.scatterplot`
                -   "matplotlib" backend: :meth:`fiftyone.core.plots.matplotlib.scatterplot`

        Returns:
            a :class:`fiftyone.core.plots.base.InteractivePlot`
        """
        if self.nearest_ids is None:
            raise ValueError(
                "You must first call `find_duplicates()` to generate results"
            )

        return fbd.visualize_duplicates(self, visualization, backend, **kwargs)

    def visualize_unique(self, visualization=None, backend="plotly", **kwargs):
        """Generates an interactive scatterplot of the results generated by the
        last call to :meth:`find_unique`.

        If the ``visualization`` argument is not provided and the embeddings
        have more than 3 dimensions, a 2D representation of the points is
        computed via :meth:`fiftyone.brain.compute_visualization`. In either
        case, the visualization used is cached on this object for subsequent
        use during the current session.

        The points are colored based on the following partition:

            -   "unique": the unique examples
            -   "other": the other examples

        You can attach plots generated by this method to an App session via its
        :attr:`fiftyone.core.session.Session.plots` attribute, which will
        automatically sync the session's view with the currently selected
        points in the plot.

        Args:
            visualization (None): a
                :class:`fiftyone.brain.visualization.VisualizationResults`
                instance to use to visualize the results
            backend ("plotly"): the plotting backend to use. Supported values
                are ``("plotly", "matplotlib")``
            **kwargs: keyword arguments for the backend plotting method:

                -   "plotly" backend: :meth:`fiftyone.core.plots.plotly.scatterplot`
                -   "matplotlib" backend: :meth:`fiftyone.core.plots.matplotlib.scatterplot`

        Returns:
            a :class:`fiftyone.core.plots.base.InteractivePlot`
        """
        if self.unique_ids is None:
            raise ValueError(
                "You must first call `find_unique()` to generate results"
            )

        return fbd.visualize_unique(self, visualization, backend, **kwargs)

    @classmethod
    def _from_dict(cls, d, samples):
        embeddings = np.array(d["embeddings"])
        config = DuplicatesConfig.from_dict(d["config"])
        return cls(samples, embeddings, config)


class DuplicatesConfig(fob.BrainMethodConfig):
    """Duplicates configuration.

    Args:
        embeddings_field (None): the sample field containing the embeddings,
            if one was provided
        model (None): the :class:`fiftyone.core.models.Model` or class name of
            the model that was used to compute embeddings, if one was provided
        patches_field (None): the sample field defining the patches being
            analyzed, if any
        metric (None): the embedding distance metric used
    """

    def __init__(
        self,
        embeddings_field=None,
        model=None,
        patches_field=None,
        metric=None,
        **kwargs,
    ):
        if model is not None and not etau.is_str(model):
            model = etau.get_class_name(model)

        self.embeddings_field = embeddings_field
        self.model = model
        self.patches_field = patches_field
        self.metric = metric
        super().__init__(**kwargs)

    @property
    def method(self):
        return "duplicates"

    @property
    def run_cls(self):
        run_cls_name = self.__class__.__name__[: -len("Config")]
        return getattr(fbd, run_cls_name)
