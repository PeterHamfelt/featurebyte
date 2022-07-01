"""
Persistent storage using Git
"""
# pylint: disable=protected-access
from __future__ import annotations

from typing import Any, Iterable, List, Literal, Optional, Tuple

import functools
import json
import os
import shutil
import tempfile
from enum import Enum

from bson import json_util
from bson.objectid import ObjectId
from git import GitCommandError
from git.remote import Remote
from git.repo.base import Repo

from featurebyte.logger import logger
from featurebyte.persistent.base import (
    Document,
    DocumentUpdate,
    DuplicateDocumentError,
    Persistent,
    QueryFilter,
)


class GitDocumentAction(str, Enum):
    """
    Enum for document action on Git repo
    """

    CREATE: str = "Create"
    UPDATE: str = "Update"
    RENAME: str = "Rename"
    DELETE: str = "Delete"


def _sync_push(func: Any) -> Any:
    """
    Synchronize git conflicts

    Parameters
    ----------
    func: Any
        Function to run

    Returns
    -------
    Any
        Return from function
    """

    @functools.wraps(func)
    def wrapper_decorator(cls: GitDB, *args: int, **kwargs: str) -> Any:
        cls._reset_branch()
        value = func(cls, *args, **kwargs)
        cls._push()
        return value

    return wrapper_decorator


class GitDB(Persistent):
    """
    Persistent storage using Git
    """

    def __init__(
        self, branch: str = "main", remote_url: Optional[str] = None, key_path: Optional[str] = None
    ) -> None:
        """
        Constructor for GitDB

        Parameters
        ----------
        branch: str
            Branch to use
        remote_url: Optional[str]
            Remote repository url
        key_path: Optional[str]
            Path to private key
        """
        self._local_path = tempfile.mkdtemp()

        if not remote_url:
            logger.warning("Remote repo not specified.")

        logger.debug("Initializing local repo", extra={"local_path": self._local_path})
        Repo.init(self._local_path)

        self._repo = repo = Repo(path=self._local_path)
        self._branch = branch
        self._ssh_cmd = f"ssh -i {key_path}" if key_path else "ssh"
        self._origin: Optional[Remote] = None
        self._working_tree_dir: str = str(repo.working_tree_dir)

        if remote_url:
            # create remote origin if does not exist
            logger.debug("Configuring remote repo", extra={"remote_url": remote_url})
            if not repo.remotes:
                repo.create_remote("origin", remote_url)
            self._origin = repo.remotes.origin

            # confirm repo has correct remote
            assert len(repo.remotes) == 1
            assert self._origin.url == remote_url

        # checkout new branch
        logger.debug("Create new branch", extra={"branch": branch})
        repo.git.checkout("-b", branch)
        try:
            # reset if remote branch exists
            assert self._origin
            self._reset_branch()
        except (GitCommandError, AttributeError, AssertionError):
            # no branch found on remote, create initial commit
            initial_commit_file_path = os.path.join(self._working_tree_dir, "README.md")
            with open(initial_commit_file_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(
                    "# FeatureByte Git Repo\nRepository for FeatureByte feature engineering SDK"
                )
            repo.git.add([initial_commit_file_path])
            repo.git.commit("-m", "Initial commit")
            self._push()

    def __del__(self) -> None:
        """
        Clean up local repo
        """
        local_path = getattr(self, "_local_path", None)
        if local_path:
            logger.debug("Delete local repo", extra={"local_path": local_path})
            shutil.rmtree(local_path)

    @property
    def repo(self) -> Repo:
        """
        Retrieve local repository

        Returns
        -------
        Repo
            Local repository
        """
        return self._repo

    def _fetch(self) -> None:
        """
        Fetch latest changes from remote
        """
        # skip if no remote
        if not self._origin:
            return

        logger.debug("Fetch latest from branch", extra={"branch": self._branch})
        with self.repo.git.custom_environment(GIT_SSH_COMMAND=self._ssh_cmd):
            self.repo.git.fetch("--depth=1", "origin", self._branch)

    def _reset_branch(self) -> None:
        """
        Reset with latest changes from remote
        """
        # skip if no remote
        if not self._origin:
            return

        logger.debug("Reset branch to remote", extra={"branch": self._branch})
        self._fetch()
        self.repo.git.reset("--hard", f"origin/{self._branch}")

    def _push(self) -> None:
        """
        Push latest changes to remote
        """
        # skip if no remote
        if not self._origin:
            return

        logger.debug("Push changes to remote branch", extra={"branch": self._branch})
        with self.repo.git.custom_environment(GIT_SSH_COMMAND=self._ssh_cmd):
            self.repo.git.push("origin", self._branch)

    def _get_collection_path(self, collection_name: str) -> str:
        """
        Get path of a directory in the repo that represents a collection

        Parameters
        ----------
        collection_name: str
            Name of collection

        Returns
        -------
        str
            Path of directory
        """
        return os.path.join(self._working_tree_dir, collection_name)

    def _get_doc_path(self, collection_path: str, doc_name: str) -> str:
        """
        Get path of a document

        Parameters
        ----------
        collection_path: str
            Path of collection directory
        doc_name: str
            Document name

        Returns
        -------
        str
            Path of document
        """
        return os.path.join(collection_path, doc_name + ".json")

    def _add_file(
        self,
        collection_name: str,
        document: Document,
        doc_name: str,
        replace: bool,
    ) -> ObjectId:
        """
        Add one file to repo

        Parameters
        ----------
        collection_name: str
            Name of collection to add document to
        document: Document
            Document to insert
        doc_name: str
            Document name
        replace: bool
            Replace existing file

        Returns
        -------
        ObjectId
            Id of inserted document

        Raises
        -------
        DuplicateDocumentError
            Document exists
        """
        # ensure collection dir exists
        collection_path = self._get_collection_path(collection_name)
        if not os.path.exists(collection_path):
            os.mkdir(collection_path)

        # ensures document id is set
        doc_id = document.get("id")
        if not doc_id:
            doc_id = ObjectId()
            document["id"] = doc_id

        # strip user id
        document.pop("user_id", None)

        # create document
        new_doc_name = document["name"]
        new_doc_path = self._get_doc_path(collection_path, new_doc_name)

        doc_exists = os.path.exists(new_doc_path)
        editing_same_file = replace and (new_doc_name == doc_name)
        if doc_exists and not editing_same_file:
            raise DuplicateDocumentError(
                f"Document {collection_name}/{new_doc_name} already exists"
            )

        # handle renaming
        is_renaming = doc_name and doc_name != new_doc_name
        if is_renaming:
            old_doc_path = self._get_doc_path(collection_path, doc_name)
            if os.path.exists(old_doc_path):
                self.repo.git.mv(old_doc_path, new_doc_path)
                self.repo.git.commit(
                    "-m",
                    f"{GitDocumentAction.RENAME} document: {collection_name}/{doc_name} -> {collection_name}/{new_doc_name}",
                )
                doc_exists = True

        action = GitDocumentAction.UPDATE if doc_exists else GitDocumentAction.CREATE
        logger.debug(f"{action} file", extra={"doc_path": new_doc_path, "replace": replace})
        with open(new_doc_path, "w", encoding="utf-8") as file_obj:
            json.dump(json.loads(json_util.dumps(document)), file_obj, indent=4)

        # commit changes
        self.repo.git.add([new_doc_path])
        # put name in commit
        self.repo.git.commit("-m", f"{action} document: {collection_name}/{new_doc_name}")

        return doc_id

    def _remove_file(self, collection_name: str, document: Document) -> None:
        """
        Remove one file from repo

        Parameters
        ----------
        collection_name: str
            Name of collection to remove document from
        document: Document
            Document to insert
        """
        # ensure collection dir exists
        collection_path = self._get_collection_path(collection_name)
        if not os.path.exists(collection_path):
            return

        # remove document
        doc_name = str(document.get("name", str(document["id"])))
        doc_path = self._get_doc_path(collection_path, doc_name)

        logger.debug("Remove file", extra={"doc_path": doc_path})
        if os.path.exists(doc_path):
            os.remove(doc_path)

        # commit changes
        self.repo.git.rm([doc_path])
        # put name in commit
        self.repo.git.commit(
            "-m", f"{GitDocumentAction.DELETE} document: {collection_name}/{doc_name}"
        )

    def _find_files(
        self, collection_name: str, query_filter: QueryFilter, multiple: bool
    ) -> List[Document]:
        """
        Find one record from collection

        Parameters
        ----------
        collection_name: str
            Name of collection to find in
        query_filter: QueryFilter
            Conditions to filter on
        multiple: bool
            Return multiple documents

        Returns
        -------
        List[Document]
            Retrieved document
        """
        # ensure collection dir exists
        collection_dir = self._get_collection_path(collection_name)
        if not os.path.exists(collection_dir):
            return []

        # check unsupported filters
        self._check_filter(query_filter)

        # strip user id
        query_filter.pop("user_id", None)
        filter_items = query_filter.items()

        documents = []
        for path in sorted(os.listdir(collection_dir)):
            with open(os.path.join(collection_dir, path), encoding="utf-8") as file_obj:
                doc: Document = json_util.loads(file_obj.read())
            if filter_items <= doc.items():
                if not multiple:
                    return [doc]
                documents.append(doc)
        return documents

    def _update_files(
        self,
        collection_name: str,
        query_filter: QueryFilter,
        update: DocumentUpdate,
        multiple: bool,
    ) -> int:
        """
        Update files in the repo

        Parameters
        ----------
        collection_name: str
            Name of collection to add document to
        query_filter: QueryFilter
            Conditions to filter on
        update: DocumentUpdate
            Values to update
        multiple: bool
            Update multiple files

        Returns
        -------
        int
            Number of documents updated
        """
        # check unsupported update
        self._check_update(update)

        docs = self._find_files(
            collection_name=collection_name, query_filter=query_filter, multiple=multiple
        )
        num_updated = 0

        for doc in docs:
            # track original doc name
            doc_name = doc["name"]
            doc.update(update["$set"])
            self._add_file(
                collection_name=collection_name,
                document=doc,
                doc_name=doc_name,
                replace=True,
            )
            num_updated += 1
        return num_updated

    def _delete_files(
        self,
        collection_name: str,
        query_filter: QueryFilter,
        multiple: bool,
    ) -> int:
        """
        Update files in the repo

        Parameters
        ----------
        collection_name: str
            Name of collection to add document to
        query_filter: QueryFilter
            Conditions to filter on
        multiple: bool
            Delete multiple files

        Returns
        -------
        int
            Number of documents delete
        """
        docs = self._find_files(
            collection_name=collection_name, query_filter=query_filter, multiple=multiple
        )
        num_deleted = 0

        for doc in docs:
            self._remove_file(collection_name=collection_name, document=doc)
            num_deleted += 1
        return num_deleted

    @staticmethod
    def _check_filter(query_filter: QueryFilter) -> None:
        """
        Validate filter is supported

        Parameters
        ----------
        query_filter: QueryFilter
            Conditions to filter on

        Raises
        ------
        NotImplementedError
            Filter is unsupported
        """
        # no period or $ in query keys
        items = [query_filter]
        while items:
            item = items.pop(0)
            for key, value in item.items():
                if "." in key:
                    raise NotImplementedError("period in key not supported")
                if "$" in key:
                    raise NotImplementedError("$ in key not supported")
                if isinstance(value, dict):
                    items.append(value)

    @staticmethod
    def _check_update(update: DocumentUpdate) -> None:
        """
        Validate update is supported

        Parameters
        ----------
        update: DocumentUpdate
            Values to update

        Raises
        ------
        NotImplementedError
            Update is unsupported
        """
        if not update:
            raise NotImplementedError("No value")

        if len(update) > 1:
            raise NotImplementedError("More than one key in top level")

        if next(iter(update.keys())) != "$set":
            raise NotImplementedError("Top key must be $set")

        if "id" in update["$set"]:
            raise NotImplementedError("ID update not supported")

        if not isinstance(update["$set"], dict):
            raise NotImplementedError("Update value must be a dict")

        # no period in update keys
        items = [update["$set"]]
        while items:
            item = items.pop(0)
            for key, value in item.items():
                if "." in key:
                    raise NotImplementedError("period in key not supported")
                if isinstance(value, dict):
                    items.append(value)

    @_sync_push
    def insert_one(self, collection_name: str, document: Document) -> ObjectId:
        """
        Insert record into collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        document: Document
            Document to insert

        Returns
        -------
        ObjectId
            Id of the inserted document
        """
        return self._add_file(
            collection_name=collection_name,
            document=document,
            doc_name=document["name"],
            replace=False,
        )

    @_sync_push
    def insert_many(self, collection_name: str, documents: Iterable[Document]) -> List[ObjectId]:
        """
        Insert records into collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        documents: Iterable[Document]
            Documents to insert

        Returns
        -------
        List[ObjectId]
            Ids of the inserted documents
        """
        doc_ids = []
        for document in documents:
            doc_ids.append(
                self._add_file(
                    collection_name=collection_name,
                    document=document,
                    doc_name=document["name"],
                    replace=False,
                )
            )
        return doc_ids

    def find_one(self, collection_name: str, query_filter: QueryFilter) -> Optional[Document]:
        """
        Find one record from collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        query_filter: QueryFilter
            Conditions to filter on

        Returns
        -------
        Optional[Document]
            Retrieved document
        """
        self._reset_branch()
        docs = self._find_files(
            collection_name=collection_name, query_filter=query_filter, multiple=False
        )
        if not docs:
            return None
        return docs[0]

    def find(
        self,
        collection_name: str,
        query_filter: QueryFilter,
        sort_by: Optional[str] = None,
        sort_dir: Optional[Literal["asc", "desc"]] = "asc",
        page: int = 1,
        page_size: int = 0,
    ) -> Tuple[Iterable[Document], int]:
        """
        Find all records from collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        query_filter: QueryFilter
            Conditions to filter on
        sort_by: Optional[str]
            Column to sort by
        sort_dir: Optional[Literal["asc", "desc"]]
            Direction to sort
        page: int
            Page number for pagination
        page_size: int
            Page size (0 to return all records)

        Returns
        -------
        Tuple[Iterable[Document], int]
            Retrieved documents and total count
        """
        sort_col = sort_by or "id"
        self._reset_branch()
        docs = self._find_files(
            collection_name=collection_name, query_filter=query_filter, multiple=True
        )
        total = len(docs)

        docs = sorted(
            docs,
            key=lambda doc: str(doc[sort_col]),
            reverse=sort_dir == "desc",
        )

        if page_size > 0:
            skips = page_size * (page - 1)
            docs = docs[skips : (skips + page_size)]

        return docs, total

    @_sync_push
    def update_one(
        self,
        collection_name: str,
        query_filter: QueryFilter,
        update: DocumentUpdate,
    ) -> int:
        """
        Update one record in collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        query_filter: QueryFilter
            Conditions to filter on
        update: DocumentUpdate
            Values to update

        Returns
        -------
        int
            Number of records modified
        """
        return self._update_files(
            collection_name=collection_name,
            query_filter=query_filter,
            update=update,
            multiple=False,
        )

    @_sync_push
    def update_many(
        self,
        collection_name: str,
        query_filter: QueryFilter,
        update: DocumentUpdate,
    ) -> int:
        """
        Update many records in collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        query_filter: QueryFilter
            Conditions to filter on
        update: DocumentUpdate
            Values to update

        Returns
        -------
        int
            Number of records modified
        """
        return self._update_files(
            collection_name=collection_name, query_filter=query_filter, update=update, multiple=True
        )

    @_sync_push
    def delete_one(self, collection_name: str, query_filter: QueryFilter) -> int:
        """
        Delete one record from collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        query_filter: QueryFilter
            Conditions to filter on

        Returns
        -------
        int
            Number of records deleted
        """
        return self._delete_files(
            collection_name=collection_name,
            query_filter=query_filter,
            multiple=False,
        )

    @_sync_push
    def delete_many(self, collection_name: str, query_filter: QueryFilter) -> int:
        """
        Delete many records from collection

        Parameters
        ----------
        collection_name: str
            Name of collection to use
        query_filter: QueryFilter
            Conditions to filter on

        Returns
        -------
        int
            Number of records deleted
        """
        return self._delete_files(
            collection_name=collection_name,
            query_filter=query_filter,
            multiple=True,
        )