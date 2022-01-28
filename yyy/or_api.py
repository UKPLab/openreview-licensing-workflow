import re

from getpass import getpass
from openreview import openreview, tools


class OpenReviewAPI:
    """
    Wraps the OpenReview API adding several convenience methods on top of the basic client abilities.
    """
    def __init__(self):
        self.user = None
        self.client = None

    def login(self):
        self.user, self.client = login()

    def blind_submissions(self, venue_id):
        invitation = venue_id + "/-/Blind_Submission"
        notes = tools.iterget_notes(self.client, invitation=invitation)

        return notes

    def reviewers(self, venue_id):
        reviewer_group_id = venue_id + "/Reviewers"
        reviewer_group = self.client.get_group(reviewer_group_id)

        return reviewer_group.members

    def reviews_by_reviewers(self, venue_id):
        """
        Retrieves reviewers that have submitted a review in the given venue. Does not account for
        assigned reviewers that haven't reviewed at all. The output is a dictionary mapping from
        reviewer ids to the list of their submitted reviews.

        :param venue_id: the id of the venue (URL of the hompage on OR)
        :return: pair of dict reviewer id to reviews and list of submissions
        """
        res = {}
        # todo for now inefficient solution via iterating all blind submissions
        blind_subs = list(self.blind_submissions(venue_id))

        for bs in blind_subs:
            revs = self.reviews_for_submission(venue_id, bs)
            for r in revs:
                rid = self.get_reviewer_id(venue_id, bs, r)
                res[rid] = [r] + res.get(rid, [])

        return res, blind_subs

    def original_for_blind_submission(self, blind_submission):
        oid = blind_submission.original
        note = self.client.get_note(id=oid)

        return note

    def reviews_for_submission(self, venue_id, blind_submission):
        invitation = venue_id + "/Paper%d/-/Official_Review" % blind_submission.number
        notes = tools.iterget_notes(self.client, invitation=invitation)

        return notes

    def consent_of_review(self, venue_id, blind_submission, review):
        review_id = review.id
        sub_id = blind_submission.id

        notes = self.client.get_notes(forum=sub_id,
                                      replyto=review_id)

        # filter for consent note
        notes = [n for n in notes if n is not None and "consent" in n.content]

        if len(notes) == 1:
            return notes[0]
        else:
            return None

    def get_reviewer_id(self, venue_id, blind_submission, review):
        signatures = review.signatures
        if len(signatures) == 1:
            sig = signatures[0]
        else:
            sig = [s for s in signatures if s.startswith(venue_id + "/Paper%d/Reviewer_" % blind_submission.number)][0]

        members = self.client.get_group(sig).members
        return members[0]

    def get_reviewer_agreement_responses(self, venue_id):
        # get response invitation
        res_id = venue_id + "/Reviewers/-/Registration"

        # get responses
        responses = list(tools.iterget_notes(self.client, invitation=res_id))
        sig_to_response = {r.signatures[0]: r for r in responses}

        if len(sig_to_response) == 0:
            raise ValueError("There are either no responses yet or no registration tasks exists for %s" % venue_id)

        return sig_to_response

    def reviewer_agreement_task(self, venue_id, title, instructions, task, start_date, due_date, exp_date):
        revs_id = venue_id + "/Reviewers"
        support_user = ""
        pcs_id = venue_id + "/Program_Chairs"

        invitees = [revs_id, support_user, pcs_id]
        readers = [venue_id, revs_id]

        form_inv_id = revs_id + "/-/Form"
        registration_inv_id = revs_id + "/-/Registration"

        # Create super invitation with a webfield
        registration_parent_invitation = openreview.Invitation(
            id=form_inv_id,
            readers=['everyone'],
            writers=[venue_id],
            signatures=[venue_id],
            invitees=invitees,
            reply={
                'forum': None,
                'replyto': None,
                'readers': {'values': readers},
                'writers': {'values': [venue_id]},
                'signatures': {'values': [venue_id]},
                'content': {
                    'title': {
                        'value': title
                    },
                    'instructions': {
                        'order': 1,
                        'value': instructions
                    }
                }
            }
        )

        # post invitation
        registration_parent_invitation = self.client.post_invitation(registration_parent_invitation)

        # registration parent note
        registration_parent = self.client.post_note(openreview.Note(
            invitation=registration_parent_invitation.id,
            readers=readers,
            writers=[venue_id],
            signatures=[venue_id],
            replyto=None,
            forum=None,
            content={
                'instructions': instructions,
                'title': title
            }
        ))

        registration_content = task
        registration_invitation = self.client.post_invitation(openreview.Invitation(
            id=registration_inv_id,
            cdate=tools.datetime_millis(start_date) if start_date else None,
            duedate=tools.datetime_millis(due_date) if due_date else None,
            expdate=tools.datetime_millis(exp_date) if exp_date else tools.datetime_millis(due_date),
            multiReply=False,
            readers=readers,
            writers=[venue_id],
            signatures=[venue_id],
            invitees=invitees,
            reply={
                'forum': registration_parent.id,
                'replyto': registration_parent.id,
                'readers': {
                    'description': 'Users who can read this',
                    'values-copied': [
                        venue_id,
                        '{signatures}'
                    ]
                },
                'writers': {
                    'description': 'How your identity will be displayed.',
                    'values-copied': [
                        venue_id,
                        '{signatures}'
                    ]
                },
                'signatures': {
                    'description': 'How your identity will be displayed.',
                    'values-regex': '~.*'
                },
                'content': registration_content
            }
        ))

        return registration_invitation

    def author_agreement_task(self, venue_id, submissions, task_name, task, start_date, due_date, exp_date):
        pcs_id = venue_id + "/Program_Chairs"

        invs = []
        for sub in submissions:
            base_id = venue_id + "/Paper%d" % sub.number
            invitees = [base_id + "/Authors"]

            inv = self.client.post_invitation(openreview.Invitation(
                id=base_id + "/-/" + task_name,
                cdate=tools.datetime_millis(start_date) if start_date else None,
                duedate=tools.datetime_millis(due_date) if due_date else None,
                expdate=tools.datetime_millis(exp_date) if exp_date else tools.datetime_millis(due_date),
                multiReply=False,
                readers=["everyone"],
                writers=[venue_id],
                signatures=[venue_id],
                invitees=invitees,
                reply={
                    'forum': sub.forum,
                    'replyto': sub.forum,
                    'readers': {
                        'description': 'Users who can read this',
                        'values-copied': [
                            pcs_id,
                            base_id + "/Authors",
                            '{signatures}'
                        ]
                    },
                    'writers': {
                        'description': 'The identity of the author.',
                        'values-copied': [
                            '{signatures}'
                        ]
                    },
                    'signatures': {
                        'description': 'How your identity will be displayed.',
                        'values-regex': base_id + '/Authors'
                    },
                    'content': task
                }
            ))
            invs += [inv]

        return invs


def get_or_client(user, password, baseurl):
    """
    Create an OpenReview client with the provided parameters or the default ones.

    :param user: the user name or email (depending on the task, should be PC for full rights)
    :param password: the password used for login
    :param baseurl: the OR API instance URL, for the dev system: https://devapi.openreview.net
    :return: the created client
    """
    or_client = openreview.Client(baseurl=baseurl, username=user, password=password)

    return or_client


def login():
    print("Please provide your user name or email on openreview.net")
    while True:
        username = input("User name = ")
        username = username.strip()
        if re.match(r"[A-Za-z0-9_\-]{1,20}", username):
            print("Username accepted")
            break

    print("Please provide your password on openreview.net")
    while True:
        password = getpass()
        if len(password) > 0:
            print("Password accepted")
            break

    return username, get_or_client(username, password, "https://api.openreview.net")