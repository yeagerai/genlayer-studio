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

### Enabling Hardhat Node
If you need to interact with a local Hardhat node for transaction processing, make sure to add the following to your `.env` file:

```
HARDHAT_URL=http://hardhat
HARDHAT_PORT=8545
COMPOSE_PROFILES=hardhat
```

This will enable the Hardhat service when running `genlayer up`.

### Disabling Hardhat Node
If you need to disable the Hardhat node, make sure to remove the following from your `.env` file:

```
HARDHAT_URL=
HARDHAT_PORT=
COMPOSE_PROFILES=
```

This will disable the Hardhat service when running `genlayer up`.

## 🚀 Key Features
* 🖥️ **Test Locally:** Developers can test Intelligent Contracts in a local environment, replicating the GenLayer network without the need for deployment. This speeds up the development cycle and reduces the risk of errors in the live environment.

* 🧪 **Versatile Scenario Testing:** The Studio allows developers to create and test contracts under various simulated network conditions. This includes stress testing under high transaction loads, simulating network delays, and testing different consensus outcomes.

* 🔄 **Changeable LLM Validators:** Developers can modify the large language models (LLMs) used by validators within the Studio. This allows for testing of security, efficiency, and accuracy by running different LLMs to validate transactions.

## 📖 The Docs
Detailed information of how to use the Studio can be found at [GenLayer Docs](https://docs.genlayer.com/).

## Contributing
As an open-source project in a rapidly developing field, we are extremely open to contributions, whether it be in the form of a new feature, improved infrastructure, or better documentation. Please read our [CONTRIBUTING](https://github.com/yeagerai/genlayer-simulator/blob/main/CONTRIBUTING.md) for guidelines on how to submit your contributions.

---

## Deployment

GenLayer Studio supports automated deployment to three separate environments — **Development**, **Staging**, and **Production** — using GitHub Actions and Ansible on Google Cloud Platform (GCP) virtual machines. Each environment has its own dedicated deployment workflow to ensure smooth CI/CD processes across the project lifecycle.

### Environments Overview

- **Development (`dev`)**  
  Used for testing new features, debugging, and integration work. Triggered via manual dispatch or push to the `main` branch in the infrastructure repository.
  **Link**: [deploy-dev.yml](https://github.com/yeagerai/genlayer-infra/actions/workflows/deploy-dev.yml)
  
- **Staging (`stage`)**  
  Mirrors production as closely as possible and is used for final QA before release. Triggered via manual dispatch or repository dispatch.
  **Link**: [deploy-stage.yml](https://github.com/yeagerai/genlayer-infra/actions/workflows/deploy-stage.yml)

- **Production (`prod`)**  
  Serves end users and contains the latest stable release. Deployments are performed manually through GitHub Actions.  
  **Link**: [deploy-prod.yml](https://github.com/yeagerai/genlayer-infra/actions/workflows/deploy-prod.yml)

### Common Deployment Flow

Each environment follows a standardized deployment sequence:

1. **Display Deployment Context**: Logs the trigger method and version being deployed.
2. **Checkout Source Code**: Retrieves the infrastructure repository codebase.
3. **Set Up Python & Dependencies**: Installs Python and required pip packages, including Ansible.
4. **Configure GCP Credentials**: Sets up service account authentication for GCP.
5. **SSH & SSL Setup**: Injects secrets-based SSH and TLS certificates.
6. **Run Ansible Playbook**: Executes deployment logic using environment-specific variables.
7. **Secrets Cleanup**: Securely removes credentials and certificates after the job completes.

Each deployment ensures security by using GitHub Actions secrets for tokens, API keys, SSH, and SSL credentials.

> ⚠️ **Important**: Make sure relevant secrets (e.g., `GCP_CREDENTIALS`, `SSH_PRIVATE_KEY`, `OPENAIKEY` etc.) are defined in the infrastructure GitHub repository for successful deployment.

---
