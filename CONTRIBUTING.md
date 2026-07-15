# Contributing

1. Create a focused branch and keep product code out of this repository.
2. Run `python -m black --check src tests` and the relevant pytest profiles.
3. Add source, license, SHA256 and `customer_data: false` for every fixture.
4. Never commit ODB/CAE files, API keys, customer models or unlicensed datasets.
5. A passing screenshot is not a substitute for numerical Abaqus assertions.

Pull requests should state the tested product commit and attach compact JUnit or
JSON evidence. Large solver artifacts stay in ignored `evidence/` storage.
