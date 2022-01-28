import argparse
import datetime
import json

from yyy import or_api


def setup_license_agreement_task_authors(api, venue_id, task_config, submission_ids=None):
    """
    Sets up the license task for authors on the OpenReview.net server

    :param api: OR api object to be used, make sure you have PC rights for the given venue
    :param venue_id: the venue id, for which you want to setup the license
    :param task_config: the configuration of the task as a dict incl. e.g. start date,...
    :param submission_ids: optionally list of submission OR ids
    :return: None
    """
    if api is None:
        # OR API
        api = or_api.OpenReviewAPI()
        api.login()

    for f in ["start", "due", "expiry", "license_form"]:
        assert f in task_config, f"{f} is missing in the task config. This field is mandatory"

    # fetch config from file
    aut_task_start, aut_task_due, aut_task_exp = task_config["start"], task_config["due"], task_config["expiry"]
    form = task_config["license_form"]

    submissions = list(api.blind_submissions(venue_id))
    if submission_ids is not None:
        submissions = [bs for bs in submissions if bs.id in submission_ids]

    api.author_agreement_task(venue_id,
                              submissions=submissions,
                              task_name="License_Agreement",
                              task=form,
                              start_date=aut_task_start,
                              due_date=aut_task_due,
                              exp_date=aut_task_exp)


def setup_license_agreement_task_reviewers(api, venue_id, task_config):
    """
    Sets up the license task for reviewers.

    :param api: OR api object to be used, make sure you have PC rights for the given venue
    :param venue_id: the venue id, for which you want to setup the license
    :param task_config: the configuration of the task as a dict incl. e.g. start date,...
    :return: None
    """
    if api is None:
        # OR API
        api = or_api.OpenReviewAPI()
        api.login()

    for f in ["start", "due", "expiry", "license_form", "title", "instructions"]:
        assert f in task_config, f"{f} is missing in the task config. This field is mandatory"

    # fetch reviewer license config
    rev_task_start, rev_task_due, rev_task_exp = task_config["start"], task_config["due"], task_config["expiry"]
    title = task_config["title"]
    instructions = task_config["instructions"]
    form = task_config["license_form"]

    api.set_reviewer_task(venue_id,
                          title=title,
                          instructions=instructions,
                          task=form,
                          start_date=rev_task_start,
                          due_date=rev_task_due,
                          exp_date=rev_task_exp)


def _parse_date(utc_date_str):
    """
    Only accepts times in AOE timezone (UTC -12h) specified in the end. The
    resulting datetime object is given in UTC, so AOE + 12h.

    :param utc_date_str: datestring matching %Y-%m-%dT%H:%M:%SAOE
    :return: the datetime matching the specified AOE time in UTC time zone
    """
    raw_date = datetime.datetime.strptime(utc_date_str, "%Y-%m-%dT%H:%M:%SAOE")
    aoe_date = raw_date + datetime.timedelta(hours=12)

    return aoe_date


def main():
    parser = argparse.ArgumentParser(description='Setup the license tasks for reviewers (and authors)')
    parser.add_argument('--venue',
                        required=True,
                        help='name of the venue in OpenReview (the base group id)')
    parser.add_argument('--license_file',
                        required=True,
                        help='path to license file to setup')
    parser.add_argument('--role',
                        required=True,
                        choices=["Reviewers", "Authors"],
                        help='the role for which the license task should be setup')
    parser.add_argument('--start_date',
                        required=True,
                        help='start date in format: %Y-%m-%dT%H:%M:%SAOE')
    parser.add_argument('--due_date',
                        required=True,
                        help='due date in format: %Y-%m-%dT%H:%M:%SAOE')
    parser.add_argument('--expiry_date',
                        required=True,
                        help='expiry date (after that date no changes possible anymore) in format: %Y-%m-%dT%H:%M:%SAOE')
    parser.add_argument('--title',
                        required=False,
                        help='if Reviewers, specify title')
    parser.add_argument('--instructions',
                        required=False,
                        help='if Reviewers, specify instructions shown at the top')
    parser.add_argument('--submissions_file',
                        required=False,
                        help='if Authors, you can specify a file with a list of OR paper IDs (one per line)')

    args = parser.parse_args()

    # create task config
    with open(args.license_file, "r") as file:
        license_form = json.load(file)

    task_config = {
        "start": _parse_date(args.start_date),
        "due": _parse_date(args.due_date),
        "expiry": _parse_date(args.expiry_date),
        "license_form": license_form
    }

    assert task_config["due"] > task_config["start"], "Due date needs to lie after the start date."
    assert task_config["expiry"] >= task_config["due"], "Expiry date needs to lie after or at the same time as due date"

    if args.title and args.instructions:
        task_config.update({
            "title": args.title,
            "instructions": args.instructions
        })

    print(f"Using the following task configuration:{task_config}")

    print("Logging into OpenReview...")
    api = or_api.login()

    if args.role == "Reviewers":
        assert "title" in task_config and "instructions" in task_config, "Reviewer license task requires title and " \
                                                                         "instructions "
        print("Creating license task for reviewers...")
        setup_license_agreement_task_reviewers(api, args.venue, task_config)
    else:
        submissions = None
        if args.submissions_file:
            with open(args.submissions_file, "r") as file:
                submissions = [l.strip() for l in file.readlines()]

        print(f"Creating license task for authors on the following submissions:")
        if submissions is not None:
            print(len(submissions), str(submissions))
        else:
            print("ALL submissions")

        setup_license_agreement_task_authors(api, args.venue, task_config, submissions)

if __name__ == "__main__":
    main()