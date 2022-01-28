import argparse
import datetime
import hashlib
import io
import json
import logging
import os
import pathlib
import random
import shutil
import string
from getpass import getpass

import pandas
import pyzipper
from tqdm import tqdm

from yyy import or_api


def retrieve_protected_data(venue,
                            target_dir,
                            anon_hash,
                            store_agreement=True,
                            password_protect=None,
                            api=None):
    """
    Retrieves the so-called protected dataset of the 3Y workflow after having setup the license tasks for
    reviewers.

    :param venue: the ID of the venue on OR (the URL of the homepage of your venue excluding the openreview.net part)
    :param target_dir: the directory to store the data
    :param anon_hash: the hash function to use for anonymizing reviewer identifiers; pass identity functiont to ignore
    :param store_agreement: True, if agreements and licenses should be stored
    :param password_protect: either one password or a pair of passwords used for the data and the licenses (second)
    :param api: the OR api object o be used
    :return: the stats of the collection?
    """
    # stats
    stats = {
        "num_subs": 0,
        "num_subs_agreed": 0,

        "num_reviewers": 0,
        "num_reviewers_agreed": 0,

        "num_active_reviewers": 0,
        "num_active_reviewers_agreed": 0,

        "num_responses": 0,
        "num_responses_attributed": 0,
        "num_active_responses": 0,
        "num_active_responses_attributed": 0,

        "num_revs_agreed_effective": 0
    }

    # output data
    dataset = {}
    agreements = []

    if api is None:
        # OR API
        api = or_api.OpenReviewAPI()
        api.login()

    # process parameters
    params = {
        "user": api.user,
        "baseurl": api.client.baseurl,
        "time": datetime.datetime.now().strftime("%Y/%m/%d, %H:%M:%S"),
        "hash": str(anon_hash)
    }

    # fetch all reviewer's agreement responses and subset of agreeing ones
    logging.info("Retrieving agreement responses for %s" % venue)
    reviewer_to_response = api.get_reviewer_agreement_responses(venue)

    reviewers_agreed = [r for r, a in reviewer_to_response.items()
                        if a.content["Agreement"].lower().strip() == "i agree"]
    reviewers_attributed = [r for r, a in reviewer_to_response.items()
                            if "attribution" in a.content and
                            a.content["attribution"].lower().strip().startswith("yes")]

    # get all reviews and select agreed ones
    reviewer_to_reviews, blind_submissions = api.reviews_by_reviewers(venue)
    pid_to_submission = {bs.id: bs for bs in blind_submissions}

    active_reviewers_agreed = [r for r in reviewers_agreed if r in reviewer_to_reviews.keys()]
    active_reviewers_attributed = [r for r in reviewers_attributed if r in reviewer_to_reviews.keys()]

    # storing actual data
    # include peer reviews without author's agreement. Only for the protected review_dataset in the vault
    # do not include submission data in any form
    logging.info("Retrieving agreed reviews of cycle %s." % venue)
    for rid in tqdm(active_reviewers_agreed):
        reviews = reviewer_to_reviews[rid]
        for r in reviews:
            sid_anon = anon_hash(r.forum)
            license = reviewer_to_response[rid]
            dataset[sid_anon] = dataset.get(sid_anon, []) + \
                                [_review_data(r, license, anon_hash, api, venue,
                                              pid_to_submission[r.forum])]

        agreement = reviewer_to_response[rid]

        agreements += [{
            "rid": rid,
            "signature": agreement.signatures,
            "writers": agreement.writers,
            "date": agreement.cdate,
            "attribution": agreement.content["attribution"] if "attribution" in agreement.content else "No",
            "reviews": [(r.forum, r.id) for r in reviews]
        }]

    # compute extended statistics
    all_reviewers = api.reviewers(venue)
    stats["num_reviewers"] = len(all_reviewers)
    stats["num_active_reviewers"] = len(reviewer_to_reviews.keys())

    stats["num_responses"] = len(reviewer_to_response.keys())
    stats["num_responses_attributed"] = len(reviewers_attributed)
    stats["num_active_responses"] = len(
        set(reviewer_to_response.keys()).intersection(set(reviewer_to_reviews.keys())))
    stats["num_active_responses_attributed"] = len(active_reviewers_attributed)

    stats["num_reviewers_agreed"] = len(reviewers_agreed)
    stats["num_active_reviewers_agreed"] = len(active_reviewers_agreed)

    # storing dataset + licenses
    if not os.path.exists(target_dir) or os.path.isfile(target_dir):
        os.mkdir(target_dir)

    _store_full_data_securely(dataset,
                              None,
                              agreements if store_agreement else None,
                              None,
                              stats,
                              params,
                              target_dir + os.sep + escape_venue_file_name(venue) + ".7z",
                              password=password_protect)

    return stats


def _review_data(review, license, anon_hash, api, venue, blind_sub):
    """
    Gets the permitted/relevant review data from the given report. In this implementation ALL fields are used,
    dates are fetched and the anonymized authors are added.

    :param review: the review Note
    :param license: the associated license (including e.g. attribution request)
    :param anon_hash: the hash used for anonymization
    :param api: the api to access OR server
    :param venue: the venue ID
    :param blind_sub: the blind submission the review refers to
    :return:
    """
    res = {
        "cdate": review.cdate,
        "tmdate": review.tmdate,
        "tauthor": anon_hash(api.get_reviewer_id(venue, blind_sub, review)),
        "signature": anon_hash(review.signatures[0]),
        "id": anon_hash(review.id)
    }
    res.update(review.content)

    res["license_date"] = license.cdate
    res["attribution"] = review.signatures[0] if "attribution" in license.content else None

    return res


def _store_full_data_securely(review_dataset, submission_dataset, rev_licenses, sub_licenses, stats, params, path,
                              prefix="", password=None):
    """
    Stores the data using the provided passwords.

    :param review_dataset: dataset of review data
    :param submission_dataset: dataset of submission data (or empty)
    :param rev_licenses: the licenses for reviews
    :param sub_licenses: the licenses for submissions
    :param stats: stats on the collection to be stored
    :param params: parameters of the collection to be stored (for reproduction)
    :param path: the path to store the data at
    :param prefix: possibly, a prefix for the file names
    :param password: the password or passwords (pair) to encrypt the data
    :return: None
    """
    # store sensitive data
    if rev_licenses is None:
        rev_licenses = []
    if sub_licenses is None:
        sub_licenses = []

    with io.BytesIO() as stream0, io.BytesIO() as stream1:
        file_names = [prefix + s for s in ["sub_licenses.csv", "rev_licenses.csv"]]

        pandas.DataFrame(rev_licenses).to_csv(stream0)
        pandas.DataFrame(sub_licenses).to_csv(stream1)
        data = [stream0, stream1]

        if type(password) == tuple:
            store_files_securely(file_names, data, path, password[1])
        else:
            store_files_securely(file_names, data, path, password)

    # store data and params
    if review_dataset is None:
        review_dataset = {}

    with io.BytesIO() as stream0, io.BytesIO() as stream1, io.BytesIO() as stream2:
        file_names = [prefix + s for s in ["rev_data.json", "params.json", "stats.json"]]

        stream0.write(json.dumps(review_dataset).encode())
        stream1.write(json.dumps(params).encode())
        stream2.write(json.dumps(stats).encode())
        data = [stream0, stream1, stream2]

        if type(password) == tuple:
            store_files_securely(file_names, data, path, password[0])
        else:
            store_files_securely(file_names, data, path, password)

    if submission_dataset is None:
        submission_dataset = {}

    with io.BytesIO() as stream0:
        file_names = [prefix + s for s in ["sub_data.json"]]

        stream0.write(json.dumps(submission_dataset).encode())
        data = [stream0]

        if type(password) == tuple:
            store_files_securely(file_names, data, path, password[0])
        else:
            store_files_securely(file_names, data, path, password)


def _load_full_data_securely(path, with_licenses, prefix="", password=None):
    """
    Loads the stored data.

    :param path: path to the directory containing the data and or licenses
    :param with_licenses: True, if licenses should also be loaded
    :param prefix: optionally a prefix for the files to load
    :param password: password or pair of passwords
    :return:
    """
    sub_license, rev_license = None, None

    # load sensitive data
    if with_licenses:
        with io.BytesIO() as stream0, io.BytesIO() as stream1:
            file_names = [prefix + s for s in ["sub_licenses.csv", "rev_licenses.csv"]]
            buffs = [stream0, stream1]

            if type(password) == tuple:
                load_files_securely(file_names, buffs, path, password[1])
            else:
                load_files_securely(file_names, buffs, path, password)

            sub_license = pandas.read_csv(stream0)
            rev_license = pandas.read_csv(stream1)

    # load review data and params
    with io.BytesIO() as stream0, io.BytesIO() as stream1, io.BytesIO() as stream2:
        file_names = [prefix + s for s in ["rev_data.json", "params.json", "stats.json"]]
        buffs = [stream0, stream1, stream2]

        if type(password) == tuple:
            load_files_securely(file_names, buffs, path, password[0])
        else:
            load_files_securely(file_names, buffs, path, password)

        review_data = json.load(stream0)
        params = json.load(stream1)
        stats = json.load(stream2)

    # load sub data
    with io.BytesIO() as stream0:
        file_names = [prefix + s for s in ["sub_data.json"]]
        buffs = [stream0]

        if type(password) == tuple:
            load_files_securely(file_names, buffs, path, password[0])
        else:
            load_files_securely(file_names, buffs, path, password)

        submission_data = json.load(stream0)

    return review_data, submission_data, params, stats, rev_license, sub_license


def load_protected_data_across_venues(dir, venues=None, password=None, with_process_data=False):
    """
    Loads stored data possibly from multiple venues stored in the same file.

    :param dir: the directory to look for data (and license) files
    :param venues: the venue ID (list of prefixes of file names within the file)
    :param password: single or pair of passwords to decrypt the files
    :param with_process_data: if true, loads meta information on the collection process too
    :return:
    """
    # check default file
    default_file = dir + os.sep + "data.7z"
    if not os.path.exists(default_file):
        raise ValueError("Passed directory does not contain a data.7z file. Aborting.")

    result_revdata, result_subdata, result_params, result_stats = {}, {}, {}, {}

    if venues is None:
        if type(password) == tuple:
            filenames = load_zip_structure_securely(default_file, password[0])
        else:
            filenames = load_zip_structure_securely(default_file, password)
        venues = [f.split("_")[0] for f in filenames]

    # access metadata file and load information
    for v in venues:
        loaded = _load_full_data_securely(default_file,
                                          with_licenses=False,
                                          prefix=escape_venue_file_name(v) + "_",
                                          password=password)
        revdata, subdata, params, stats = loaded[0], loaded[1], loaded[2], loaded[3]

        result_revdata[v] = revdata
        result_subdata[v] = subdata
        result_params[v] = params
        result_stats[v] = stats

    if with_process_data:
        return result_revdata, result_subdata, result_params, result_stats
    else:
        return result_revdata, result_subdata


def escape_venue_file_name(venue):
    """
    Escapes the venue name (OR ID) to be formatted appropriately for storing. Deterministic.

    :param venue: venue name
    :return: escaped string
    """
    return "".join(x for x in venue if x.isalnum())


def random_salt(length):
    """
    Returns a random salt to be used. Warning: no cryptographic guarantees.

    :param length: length of the salt string in characters
    :return:
    """
    return ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(length))


def load_zip_structure_securely(path, password):
    """
    Loads a AES encrypted zip file structure.

    :param path: path to file
    :param password: used password
    :return: the loaded files from within the zip
    """
    with pyzipper.AESZipFile(path, 'r', compression=pyzipper.ZIP_LZMA) as zf:
        if password is not None:
            zf.setpassword(bytes(password, 'utf-8'))
            zf.setencryption(pyzipper.WZ_AES, nbits=256)

        contained_files = zf.namelist()

    return contained_files


def load_files_securely(file_names, target_buffers, path, password):
    """
    Loads the files contained in an AES encrypted zip file.

    :param file_names: list of files to load from the zip
    :param target_buffers: list of buffers to read the result into
    :param path: the path to the file to be loaded
    :param password: the password used during encryption
    :return: void
    """
    with pyzipper.AESZipFile(path, 'r', compression=pyzipper.ZIP_LZMA) as zf:
        if password is not None:
            zf.setpassword(bytes(password, 'utf-8'))
            zf.setencryption(pyzipper.WZ_AES, nbits=256)

        for fn, buff in zip(file_names, target_buffers):
            with zf.open(fn, "r") as file:
                buff.write(file.read())
                buff.seek(0)


def store_files_securely(file_names, data, path, password):
    """
    Stores the given files within an AES encrypted zip file.

    :param file_names: list of file names
    :param data: associated buffers, one per file name
    :param path: the path to store
    :param password: the password to use
    :return: void
    """
    if not os.path.exists(path):
        pathlib.Path(path).touch()

    with pyzipper.AESZipFile(path, 'a', compression=pyzipper.ZIP_LZMA) as zf:
        if password is not None:
            zf.setpassword(bytes(password, 'utf-8'))
            zf.setencryption(pyzipper.WZ_AES, nbits=256)

        for n, d in zip(file_names, data):
            with zf.open(n, 'w') as file:
                file.write(d.getvalue())


def copy_readme(path, readme_path="resources/README.md"):
    """
    Copies readme with instructions on how to load the encrypted zip files into the same directory.

    :param path:
    :param readme_path:
    :return:
    """
    shutil.copyfile(readme_path, path + os.sep + "README.md")


class HashWrapper():
    """
    Convenience wrapper for a hash function. You may specify the function itself, a used salt and
    repetitions. Calling str() on this object returns the list of used parameters to recreate this
    configuration.
    """
    def __init__(self, hash, salt, repetitions=1):
        self.hash = hash
        self.salt = salt
        self.repetitions = repetitions

    def __call__(self, input):
        res = self.hash(self.salt + input.encode("utf-8")).hexdigest()
        for i in range(res-1):
            res = self.hash(res.encode("utf-8")).hexdigest()

        return res

    def __str__(self):
        return "ALGO:%s;REPETITIONS:%d;SALT:%s" % (str(self.hash), self.repetitions, str(self.salt))


def main():
    parser = argparse.ArgumentParser(description='Fetch the peer review data and licenses from OR.')
    parser.add_argument('--venue',
                        required=True,
                        help='name of the venue in OpenReview (the base group id)')
    parser.add_argument('--target_dir',
                        required=True,
                        help='path (without spaces) to the directory, where data will be put (created if non-existent)')
    parser.add_argument('--store_agreement',
                        required=True,
                        choices=["yes", "no"],
                        help='yes, if non-anonymized consents should be stored (in a separate file)')
    parser.add_argument('--pwd_protect',
                        required=True,
                        choices=["yes", "no"],
                        help='yes, you will need to enter a password and the files will be encrypted using this')
    parser.add_argument('--hash',
                        required=False,
                        choices=["SHA-512"],
                        help='the hashing algorithm to be used.')
    parser.add_argument('--salt',
                        required=False,
                        choices=["yes", "no"],
                        help='sets the salt of the hashing algorithm explicitly; asked to enter on prompt.')

    args = parser.parse_args()

    dir = args.target_dir
    agreement = args.store_agreement == "yes"
    pwd_protect = args.pwd_protect == "yes"
    if pwd_protect:
        print("You have selected the option to encrypt the review data using a password. Please enter...")
        while True:
            password = getpass()
            if len(password) >= 6:
                print("Password accepted")
                break
            else:
                print("Password length needs to be >= 6")

        if agreement:
            print("You have selected to store license agreements and to protect it with a password. Please enter...")
            while True:
                password_l = getpass()
                if len(password_l) >= 6:
                    print("Password accepted")
                    break
                else:
                    print("Password length needs to be >= 6")
        else:
            password_l = None

        if password == password_l:
            print("Having the same password for storing licenses and data is *strongly* discouraged!")
    else:
        password = None
        password_l = None

    fun = hashlib.sha512
    if args.salt is not None:
        print("You selected a pre-defined salt. Please enter...")
        while True:
            salt_in = getpass()
            if len(salt_in) > 0:
                print("Salt accepted")
                salt = salt_in.encode("utf-8")
                break
            else:
                print("Salt empty. Retry...")
    else:
        salt = random_salt(32).encode("utf-8")
    hash = HashWrapper(fun, salt, repetitions=10000)  # default ot 10000 repetitions for security

    retrieve_protected_data(venue=args.venue,
                            target_dir=dir,
                            anon_hash=hash,
                            store_agreement=agreement,
                            password_protect=(password, password_l))


if __name__ == "__main__":
    main()

