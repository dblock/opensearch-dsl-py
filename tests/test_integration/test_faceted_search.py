#  Licensed to Elasticsearch B.V. under one or more contributor
#  license agreements. See the NOTICE file distributed with
#  this work for additional information regarding copyright
#  ownership. Elasticsearch B.V. licenses this file to you under
#  the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
# 	http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.

from datetime import datetime

import pytest

from opensearch_dsl import A, Boolean, Date, Document, Keyword
from opensearch_dsl.faceted_search import (
    DateHistogramFacet,
    FacetedSearch,
    NestedFacet,
    RangeFacet,
    TermsFacet,
)

from .test_document import PullRequest


class Repos(Document):
    is_public = Boolean()
    created_at = Date()

    class Index:
        name = "git"


class Commit(Document):
    files = Keyword()
    committed_date = Date()

    class Index:
        name = "git"


class MetricSearch(FacetedSearch):
    index = "git"
    doc_types = [Commit]

    facets = {
        "files": TermsFacet(field="files", metric=A("max", field="committed_date")),
    }


@pytest.fixture(scope="session")
def commit_search_cls(es_version):
    interval_kwargs = {"fixed_interval": "1d"}

    class CommitSearch(FacetedSearch):
        index = "flat-git"
        fields = (
            "description",
            "files",
        )

        facets = {
            "files": TermsFacet(field="files"),
            "frequency": DateHistogramFacet(
                field="authored_date", min_doc_count=1, **interval_kwargs
            ),
            "deletions": RangeFacet(
                field="stats.deletions",
                ranges=[("ok", (None, 1)), ("good", (1, 5)), ("better", (5, None))],
            ),
        }

    return CommitSearch


@pytest.fixture(scope="session")
def repo_search_cls(es_version):
    interval_type = "calendar_interval"

    class RepoSearch(FacetedSearch):
        index = "git"
        doc_types = [Repos]
        facets = {
            "public": TermsFacet(field="is_public"),
            "created": DateHistogramFacet(
                field="created_at", **{interval_type: "month"}
            ),
        }

        def search(self):
            s = super(RepoSearch, self).search()
            return s.filter("term", commit_repo="repo")

    return RepoSearch


@pytest.fixture(scope="session")
def pr_search_cls(es_version):
    interval_type = "calendar_interval"

    class PRSearch(FacetedSearch):
        index = "test-prs"
        doc_types = [PullRequest]
        facets = {
            "comments": NestedFacet(
                "comments",
                DateHistogramFacet(
                    field="comments.created_at", **{interval_type: "month"}
                ),
            )
        }

    return PRSearch


def test_facet_with_custom_metric(data_client):
    ms = MetricSearch()
    r = ms.execute()

    dates = [f[1] for f in r.facets.files]
    assert dates == list(sorted(dates, reverse=True))
    assert dates[0] == 1399038439000


def test_nested_facet(pull_request, pr_search_cls):
    prs = pr_search_cls()
    r = prs.execute()

    assert r.hits.total.value == 1
    assert [(datetime(2018, 1, 1, 0, 0), 1, False)] == r.facets.comments


def test_nested_facet_with_filter(pull_request, pr_search_cls):
    prs = pr_search_cls(filters={"comments": datetime(2018, 1, 1, 0, 0)})
    r = prs.execute()

    assert r.hits.total.value == 1
    assert [(datetime(2018, 1, 1, 0, 0), 1, True)] == r.facets.comments

    prs = pr_search_cls(filters={"comments": datetime(2018, 2, 1, 0, 0)})
    r = prs.execute()
    assert not r.hits


def test_datehistogram_facet(data_client, repo_search_cls):
    rs = repo_search_cls()
    r = rs.execute()

    assert r.hits.total.value == 1
    assert [(datetime(2014, 3, 1, 0, 0), 1, False)] == r.facets.created


def test_boolean_facet(data_client, repo_search_cls):
    rs = repo_search_cls()
    r = rs.execute()

    assert r.hits.total.value == 1
    assert [(True, 1, False)] == r.facets.public
    value, count, selected = r.facets.public[0]
    assert value is True


def test_empty_search_finds_everything(data_client, es_version, commit_search_cls):
    cs = commit_search_cls()
    r = cs.execute()

    assert r.hits.total.value == 52
    assert [
        ("elasticsearch_dsl", 40, False),
        ("test_elasticsearch_dsl", 35, False),
        ("elasticsearch_dsl/query.py", 19, False),
        ("test_elasticsearch_dsl/test_search.py", 15, False),
        ("elasticsearch_dsl/utils.py", 14, False),
        ("test_elasticsearch_dsl/test_query.py", 13, False),
        ("elasticsearch_dsl/search.py", 12, False),
        ("elasticsearch_dsl/aggs.py", 11, False),
        ("test_elasticsearch_dsl/test_result.py", 5, False),
        ("elasticsearch_dsl/result.py", 3, False),
    ] == r.facets.files

    assert [
        (datetime(2014, 3, 3, 0, 0), 2, False),
        (datetime(2014, 3, 4, 0, 0), 1, False),
        (datetime(2014, 3, 5, 0, 0), 3, False),
        (datetime(2014, 3, 6, 0, 0), 3, False),
        (datetime(2014, 3, 7, 0, 0), 9, False),
        (datetime(2014, 3, 10, 0, 0), 2, False),
        (datetime(2014, 3, 15, 0, 0), 4, False),
        (datetime(2014, 3, 21, 0, 0), 2, False),
        (datetime(2014, 3, 23, 0, 0), 2, False),
        (datetime(2014, 3, 24, 0, 0), 10, False),
        (datetime(2014, 4, 20, 0, 0), 2, False),
        (datetime(2014, 4, 22, 0, 0), 2, False),
        (datetime(2014, 4, 25, 0, 0), 3, False),
        (datetime(2014, 4, 26, 0, 0), 2, False),
        (datetime(2014, 4, 27, 0, 0), 2, False),
        (datetime(2014, 5, 1, 0, 0), 2, False),
        (datetime(2014, 5, 2, 0, 0), 1, False),
    ] == r.facets.frequency

    assert [
        ("ok", 19, False),
        ("good", 14, False),
        ("better", 19, False),
    ] == r.facets.deletions


def test_term_filters_are_shown_as_selected_and_data_is_filtered(
    data_client, commit_search_cls
):
    cs = commit_search_cls(filters={"files": "test_elasticsearch_dsl"})

    r = cs.execute()

    assert 35 == r.hits.total.value
    assert [
        ("elasticsearch_dsl", 40, False),
        ("test_elasticsearch_dsl", 35, True),  # selected
        ("elasticsearch_dsl/query.py", 19, False),
        ("test_elasticsearch_dsl/test_search.py", 15, False),
        ("elasticsearch_dsl/utils.py", 14, False),
        ("test_elasticsearch_dsl/test_query.py", 13, False),
        ("elasticsearch_dsl/search.py", 12, False),
        ("elasticsearch_dsl/aggs.py", 11, False),
        ("test_elasticsearch_dsl/test_result.py", 5, False),
        ("elasticsearch_dsl/result.py", 3, False),
    ] == r.facets.files

    assert [
        (datetime(2014, 3, 3, 0, 0), 1, False),
        (datetime(2014, 3, 5, 0, 0), 2, False),
        (datetime(2014, 3, 6, 0, 0), 3, False),
        (datetime(2014, 3, 7, 0, 0), 6, False),
        (datetime(2014, 3, 10, 0, 0), 1, False),
        (datetime(2014, 3, 15, 0, 0), 3, False),
        (datetime(2014, 3, 21, 0, 0), 2, False),
        (datetime(2014, 3, 23, 0, 0), 1, False),
        (datetime(2014, 3, 24, 0, 0), 7, False),
        (datetime(2014, 4, 20, 0, 0), 1, False),
        (datetime(2014, 4, 25, 0, 0), 3, False),
        (datetime(2014, 4, 26, 0, 0), 2, False),
        (datetime(2014, 4, 27, 0, 0), 1, False),
        (datetime(2014, 5, 1, 0, 0), 1, False),
        (datetime(2014, 5, 2, 0, 0), 1, False),
    ] == r.facets.frequency

    assert [
        ("ok", 12, False),
        ("good", 10, False),
        ("better", 13, False),
    ] == r.facets.deletions


def test_range_filters_are_shown_as_selected_and_data_is_filtered(
    data_client, commit_search_cls
):
    cs = commit_search_cls(filters={"deletions": "better"})

    r = cs.execute()

    assert 19 == r.hits.total.value


def test_pagination(data_client, commit_search_cls):
    cs = commit_search_cls()
    cs = cs[0:20]

    assert 52 == cs.count()
    assert 20 == len(cs.execute())
