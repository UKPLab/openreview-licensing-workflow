import copy
import logging

from yyy.collect import load_protected_data_across_venues


def load_vault_data(parent_dir, password):
    """
    Loads the protected (or "vault") dataset from the provided directory and the given password(s).
    They are parsed into a VenueDataset each and added to a MultiVenueDataset.
    :param parent_dir: the directory to load from
    :param password: password or pair of passwords encrypting the files
    :return: the MultiVenueDataset loaded from disc
    """
    fullrev_data, fullsub_data, fparams, fstats = load_protected_data_across_venues(parent_dir,
                                                                                    venues=None,
                                                                                    password=password,
                                                                                    with_process_data=True)

    venues = {}
    for v in fullrev_data:
        reviews = {pid: {r["id"]: Review(r, r["id"], r["tauthor"]) for r in revs}
                   for pid, revs in fullrev_data[v].items()}
        submissions = {pid: sub for pid, sub in fullsub_data[v].items()}
        if len(submissions) == 0:
            submissions = {s: Submission({}, s) for s in reviews}

        name = v + "_full_" + fparams[v]["time"]

        cd = VenueDataset(submissions, reviews, {"full_name": name,
                                                 "full_stats": fstats[v]
                                                 })
        venues[v] = cd

    return MultiVenueDataset(venues)


class Review:
    """
    Describes a review report with metadata. The contents are dicts of fields. Each review has
    a unique RID and is associated with exactly one reviewer (by their unique ID).
    """
    def __init__(self, content: dict, rid: str, reviewer: str):
        self.content = content
        self.rid = rid
        self.reviewer = reviewer

    def __getitem__(self, item):
        return self.content[item]

    def __delitem__(self, key):
        del self.content[key]

    def __setitem__(self, key, value):
        self.content[key] = value

    def __eq__(self, other):
        return self.rid == other.rid

    def __iter__(self):
        for item in self.content:
            yield item


class Submission:
    """
    Describes a submission to a venue. The contents are dicts of fields. Each subission
    has a unique SID.
    """
    def __init__(self, content: dict, sid: str):
        self.content = content
        self.sid = sid

    def __getitem__(self, item):
        return self.content[item]

    def __delitem__(self, key):
        del self.content[key]

    def __setitem__(self, key, value):
        self.content[key] = value

    def __eq__(self, other):
        return self.sid == other.sid

    def __iter__(self):
        for item in self.content:
            yield item


class PerSubmissionIndex:
    """
    Iterate over the peer reviewing data on a per-submission basis.
    """
    def __init__(self, submissions, reviews):
        self.submissions = submissions
        self.reviews = reviews

    def __getitem__(self, item):
        sub = self.submissions[item]
        revs = self.reviews[item]

        return sub, revs

    def __delitem__(self, key):
        del self.submissions[key]
        del self.reviews[key]

    def __setitem__(self, key, value):
        submission, reviews = value
        self.submissions[key] = submission
        self.reviews[key] = reviews

    def __iter__(self):
        for sid in self.submissions:
            yield sid

    def __len__(self):
        return len(self.submissions)


class PerReviewerIndex:
    """
    Access the peer reviewing data on a per-reviewer basis. Iterate over reviewers to
    get the reviews with associated submissions they reviewed.
    """
    def __init__(self, submissions, reviews):
        self.submissions = submissions
        self.reviews = reviews

        self._compute_index()

    def _compute_index(self):
        self.index = {}
        for sid, revs in self.reviews.items():
            for rid, r in revs.items():
                reviewer = r.reviewer
                self.index[reviewer] = self.index.get(reviewer, []) + [(sid, r.rid)]

    def __getitem__(self, item):  # item == reviewer id
        reviewed_ids = self.index[item]

        reviews = {}
        subs = []
        for sid, rev_id in reviewed_ids:
            if sid in reviews:
                prev = reviews[sid]
            else:
                prev = {}

            prev[rev_id] = list(r[1] for r in filter(lambda x: x[0] == rev_id, self.reviews[sid].items()))[0]
            reviews[sid] = prev

            subs += [self.submissions[sid]]

        return subs, reviews

    def __delitem__(self, key):  # key == reviewer id
        reviewed_ids = self.index[key]

        del self.index[key]
        for sid, rev_id in reviewed_ids:
            del self.reviews[sid][rev_id]

    def __setitem__(self, key, value):  # key == reviewer id, value == submissions, reviews
        submissions, reviews = value

        self.__delitem__(key)

        for subid in submissions:
            if subid not in self.submissions:
                self.submissions[subid] = submissions[subid]

        for subid, reviews in reviews.items():
            for rev_id, review in reviews.items():
                self.reviews[subid][rev_id] = self.reviews[subid][rev_id]
                self.index[key] = self.index.get(key, []) + [(subid, rev_id)]

    def __iter__(self):
        for reviewer_id in self.index:
            yield reviewer_id

    def __len__(self):
        return len(self.index)


class VenueDataset:
    """
    This class connects several views and convenience methods for merging and accessing a
    venue. It stores the peer reviews per submission associated with reviewers while
    granting per-submission and per-reviewer access during iteration.
    This object can be merged with other VenueDatasets using <<, where the left operands
    (this objects) reviews are kept in the case of collisions.
    """
    def __init__(self, submissions: dict, reviews: dict, desc: dict):
        self.submissions = submissions
        self.reviews = reviews

        self.per_sub = PerSubmissionIndex(self.submissions, self.reviews)
        self.per_reviewer = PerReviewerIndex(self.submissions, self.reviews)

        self.desc = desc

    def __lshift__(self, other):
        new_submissions = copy.deepcopy(self.submissions)
        new_reviews = copy.deepcopy(self.reviews)
        new_desc = copy.deepcopy(self.desc)

        # to update description
        sub_conflicting = []
        sub_overlap = []
        rev_overlap = []

        for sid, sub in other.submissions.items():
            if sid not in new_submissions:
                new_submissions[sid] = sub
            elif sid in new_submissions and sub != new_submissions[sid]:
                logging.warning("Merging two datasets with differing submissions. Will keep left OPs data.")
                sub_conflicting += [sid]
            elif sid in new_submissions:  # submissions covered by both datasets
                sub_overlap += [sid]

        for sid, reviews in other.reviews.items():
            if sid not in new_reviews:
                new_reviews[sid] = {}

            for r in reviews:
                if r in new_reviews[sid]:
                    logging.warning("Merging two datasets with conflicting reviews. Will keep left OPs data.")
                    rev_overlap += [r]
                else:
                    new_reviews[sid][r] = reviews[r]

        new_desc.update(other.desc)
        new_desc["conflicting_submissions"] = sub_conflicting
        new_desc["overlapping_submissions"] = sub_overlap
        new_desc["overlapping_reviews"] = rev_overlap

        return VenueDataset(new_submissions, new_reviews, new_desc)


class MultiVenueDataset:
    """
    Class for ease of management of multiple (sequential) venues. This object can be merged with other
    MultiVenueDatasets covering the same venues (by name or position in the list) while merging these
    on a per-review and per-submission basis. Use: a << b. Outcome contains merged venues of a and b
    without altering a or b.
    """
    def __init__(self, venues):
        if type(venues) == list:
            self.venues = {i: c for (i, c) in enumerate(venues)}
        elif type(venues) == dict:
            self.venues = venues
        else:
            raise ValueError("Passed venue object is of type %s. Expected list or dict." % str(type(venues)))

    def __getitem__(self, item):
        return self.venues[item]

    def __delitem__(self, key):
        del self.venues[key]

    def __setitem__(self, key, value):
        self.venues[key] = value

    def __iter__(self):
        for c in self.venues:
            yield c

    def __lshift__(self, other):
        new_venues = {}
        for k, v in self.venues.items():
            new_v = copy.deepcopy(v)
            new_venues[k] = new_v

        for k, v in other.venues.items():
            new_v = copy.deepcopy(v)

            if k in new_venues:
                new_venues[k] <<= new_v
            else:
                new_venues[k] = new_v

        return MultiVenueDataset(new_venues)
