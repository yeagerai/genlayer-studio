# TODO

Some of these tests are not working

- [ ] Fix them
- [ ] Create a GitHub Action to run them in CI

# SQLAlchemy integration tests

## Why

Integration tests allow us to rapidly catch runtime errors (very common in languages like Python) locally, prior to releases

## What

### What they are

These tests test our integration with an actual `postgres` database. That's why this need its own environment by setting up a private postgres db just for testing

These tests are standalone, they don't require the Studio to be up

### What they are not

We are not unit testing the module here because that requires a lot of mocking, which is not really valuable since the registry logic is pretty simple

- most content online suggest connecting to a database, almost always suggesting in memory `sqlite` as in https://coderpad.io/blog/development/a-guide-to-database-unit-testing-with-pytest-and-sqlalchemy/
  - we cannot go with this approach since the `JSONB` type of `postgres` is a custom `dialect`, and we are using it in most of our models. Maybe at some point `SQLAlchemy`'s' `JSONB` will be inter-compatible between `sqlite` and `postgres` :https://sqlite.org/draft/jsonb.html
    https://github.com/miki725/alchemy-mock
- mocking alternatives need to be mocked very precisely: this makes the tests ["white-boxed"](https://en.wikipedia.org/wiki/White-box_testing) which is not great because we wouldn't be testing behavior
  - https://github.com/miki725/alchemy-mock

## Usage

These tests are expected to be run from the root of the repository

```sh
docker compose -f tests/db-sqlalchemy/docker-compose.yml --project-directory . up tests --build --force-recreate --always-recreate-deps
```

If your `postgres` database has information you want to clean, run

```sh
docker compose -f tests/db-sqlalchemy/docker-compose.yml --project-directory . down
```

## Future possible improvements

- GitHub Action to test this in CI
- Allow attaching debugger to the container
- Review how to integrate the codebase in a more streamlined way
  - at the moment we have our custom `requirements.txt`, which will probably get desyncronized at some point
  - module management is also a bit manual, directories are manipulated for imports to resolve correctly
