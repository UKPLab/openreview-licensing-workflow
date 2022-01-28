## OpenReview License Dataset
### Opening the files
The files are encrypted using AES w/ 256bits. On Ubuntu you need to install 
the p7zip-full package to unzip these files (this should also work from the
file viewer then).

`` sudo apt-get install p7zip-full ``

Upon extraction (either by command line or UI) you need to enter the password
provided by your data administrator. 

For loading the data into your processing system and to avoid having to extract
it in an insecure environment, we recommend using the methods provided in the
`meta_data.py` based on `pyzipper` (version, see requirements file).

If you should lose the password, you won't be able to access the data anymore!

### Anonymization and Identity Management
The result of running a data fetch are two files, each encrypted by the same
password. The first contains the metadata, the later the non-anonymized consent
information (for legal purposes). You should keep these files separate from
one another and only (if at all) distribute the anonymized metadata.

The metadata is anonymized by replacing the reviewer identifiers through the hashed
version (+ random salt).

The salt and hashing algorithm type are stored under the paramter files in the
encrypted directories. You need these to replicate the identifiers.

Note: The produced dataset has no privacy guarantees. You should NOT release the
resulting data as-is.