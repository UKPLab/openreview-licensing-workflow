# Yes-Yes-Yes: Licensing Workflow for an OpenReview-based Peer Reviewing Data Collection on a Donation-basis

This repo provides code to set up a licensing workflow for peer review data and paper drafts submitted
to OpenReview-based venues. This repo is constantly evolving and provides (as of now) the implementation
for creating license tasks for reviewers and authors of selected submissions, as well as the code
for retrieving the protected (for an explanation, see the [associated preprint](https://arxiv.org/abs/2201.11443)) dataset of peer reviews in a privacy- and anonymity-aware fashion.

## Overview
There are four main components in this repo for realizing the 3Y Workflow. The code is structured as follows:

``` 
> resources             [example license texts]
> yyy                   [code for 3Y Workflow]
  > collect.py          [retrieve and store donated data]
  > data.py             [loading of retrieved data]
  > license_setup.py    [license task setup in OR]
  > or_api.py           [wrapper for OR API]
```

## Setting up Your Venue
Run `license_setup.py` providing the necessary parameters. To setup the task for reviewers you specify
the `role` parameter as `Reviewers`. Decide on the relevant dates and instructions for reviewers. Note: The
due date marks the time until when reviewers are asked to finish the task, but they can still submit a response
afterwards up until the expiry date has passed. If you do not want to differentiate that, you set them to the
same time. 

To create the license task for authors, which appears for them in the respective paper forum as a button at the
top, you run the script providing `Authors` for the `role` parameter. To realize the collection considering the 3Y
schema you should also pass the list of accepted papers (by their OpenReview identifiers being the part that follows
after `https://openreview.net/forum?id=` in the paper forum URL or when using the OpenReview API the `id` field
of a retrieved submission `Note`).

If you want to use this implementation in a different research community or for a different peer reviewing campaign than ACL and ARR, 
please carefully read the provided license agreement texts resources/arr_{reviewer/author}_license.json and adapt them to the publishing practices in your community.

> DISCLAIMER: The provided license agreements serve as a point of reference for the design of such an agreement for other venues and communities. 
 We give no warranties for the legal implications of re-using the provided texts, and highly encourage discussing the draft of a license with the parties responsible for the publishing, dissemination and archival in your community.

## Retrieving Data
This code base (as of now) supports the retrieval of the protected dataset of peer reviews along
with their associated licenses (stored in a separate file). There will be an update to retrieve the public dataset
including submission data of agreeing authors for the set of accepted papers. 

To retrieve the protected dataset, run `collect.py` providing the venue parameters, passwords and salts.
The resulting dataset will be stored in enrypted zip-files. Please check out the readme in the resulting
files describing how to unpack them. We highly recommend using different passwords for the license file
and the actual data file.

> DISCLAIMER: The provided implementation for data retrieval and storing may not guarantee full anonymity or confidentiality, it is only given as a reference for desinging the retrieval. Please consider using cryptographically secure methods for storage with proper access right management. As peer reviews contain textual data, they might breach confidential information on their authors or the paper they assess. 

## Using Data
To load the retrieved data you can use the `load_vault_data()` method provided in `data.py`. You can
load multiple venues into a `MultiVenueDataset` containing a sequence of `VenueDataset` objects.
Both classes offer convenience operators for merging. To access the reviews in a `VenueDataset` you
can either use its `per_sub` index (iterate over submissions with associated reviews) or its
`per_reviewer` index (iterate over reviewers with associated reviews and submissions).

Also check out the following references on the OpenReview API to understand the
internal datastructures used, such as `Notes` or `Groups`:
* [OpenReview.net API](https://api.openreview.net/api/)
* [OpenReview.net Python Client](https://openreview-py.readthedocs.io/en/latest/)

## Citing & Authors
If you find this repository helpful or you apply the 3Y-Workflow for your data collection, please cite our pre-print [Yes-Yes-Yes: Donation-based Peer Reviewing Data Collection for ACL Rolling Review and Beyond](https://arxiv.org/abs/2201.11443):
```bibtex 
@misc{dycke2022yesyesyes,
      title={Yes-Yes-Yes: Donation-based Peer Reviewing Data Collection for ACL Rolling Review and Beyond}, 
      author={Nils Dycke and Ilia Kuznetsov and Iryna Gurevych},
      year={2022},
      eprint={2201.11443},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
```

## Contact
Don't hesitate to send us an e-mail or report an issue, if something is broken (and it shouldn't be) or if you have further questions.

**Contact persons:** Nils Dycke, Ilia Kuznetsov

https://www.ukp.tu-darmstadt.de/

https://www.tu-darmstadt.de/

> This repository contains experimental software and is published for the sole purpose of giving additional background details on the respective publication.
