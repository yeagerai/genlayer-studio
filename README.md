# GenLayer Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/license/mit/) [![Discord](https://dcbadge.vercel.app/api/server/8Jm4v89VAu?compact=true&style=flat)](https://discord.gg/VpfmXEMN66) [![Twitter](https://img.shields.io/twitter/url/https/twitter.com/yeagerai.svg?style=social&label=Follow%20%40GenLayer)](https://x.com/GenLayer) [![GitHub star chart](https://img.shields.io/github/stars/yeagerai/genlayer-simulator?style=social)](https://star-history.com/#yeagerai/genlayer-simulator)

## 👀 About

This Studio is an interactive sandbox designed for developers to explore the potential of the [GenLayer Protocol](https://genlayer.com/). It replicates the GenLayer network's execution environment and consensus algorithm, but offers a controlled and local environment to test different ideas and behaviors.

## Prerequisites
Before installing the GenLayer CLI, ensure you have the following prerequisites installed:

- [Docker](https://docs.docker.com/engine/install/): Required to run the GenLayer environment. **Required version**: Docker 26+
- [Node.js and npm](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm/): Needed for the GenLayer CLI tool. **Required version**: Node.js 18+

## 🛠️ Installation and usage

```
$ npm install -g genlayer
$ genlayer init
```

To run genlayer again just run:

```
$ genlayer up
```
After executing those commands a new tab will open in your browser with the GenLayer Studio. Additional installation instructions can be found [here](https://docs.genlayer.com/simulator/installation)

## 🚀 Key Features
* 🖥️ **Test Locally:** Developers can test Intelligent Contracts in a local environment, replicating the GenLayer network without the need for deployment. This speeds up the development cycle and reduces the risk of errors in the live environment.

* 🧪 **Versatile Scenario Testing:** The Studio allows developers to create and test contracts under various simulated network conditions. This includes stress testing under high transaction loads, simulating network delays, and testing different consensus outcomes.

* 🔄 **Changeable LLM Validators:** Developers can modify the large language models (LLMs) used by validators within the Studio. This allows for testing of security, efficiency, and accuracy by running different LLMs to validate transactions.


## 📖 The Docs
Detailed information of how to use the Studio can be found at [GenLayer Docs](https://docs.genlayer.com/).

### Production Server Setup
The application now uses Gunicorn as the production-grade WSGI server for both `backend` and `webrequest` containers. Ensure that Gunicorn is configured properly in the Dockerfiles.

## 🧪 Testing

To ensure high-quality contributions, run all tests and generate coverage reports before submitting a pull request:

```sh
$ pytest --cov=backend --cov=webrequest --cov-report=xml
```

## Contributing
As an open-source project in a rapidly developing field, we are extremely open to contributions, whether it be in the form of a new feature, improved infrastructure, or better documentation. Please read our [CONTRIBUTING](https://github.com/yeagerai/genlayer-simulator/blob/main/CONTRIBUTING.md) for guidelines on how to submit your contributions.
