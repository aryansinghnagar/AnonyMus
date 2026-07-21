# AnonyMus

AnonyMus is a metadata-resistant, privacy-focused instant messenger operating over a dual-mode centralized relay or P2P Onion-routed transport. It implements state-of-the-art cryptographic primitives, including double-ratcheted E2EE, ML-KEM-768 post-quantum key encapsulation, and client-side contact blocklists.

[![CI Status](https://github.com/aryansinghnagar/AnonyMus/actions/workflows/python.yml/badge.svg)](https://github.com/aryansinghnagar/AnonyMus/actions)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Reproducible Builds](https://img.shields.io/badge/Reproducible_Builds-passing-success)](https://github.com/aryansinghnagar/AnonyMus)

---

## Quick Links

* **Getting Started**: [Setup Guide](file:///docs/guides/setup.md)
* **Architecture Specification**: [Overview & Design](file:///docs/architecture/overview.md)
* **API Documentation**: [REST & Socket.IO Events](file:///docs/api/socket-io-events.md)
* **Self-Hosting**: [Self-Host Guide](file:///docs/guides/self-hosting.md)
* **Master Testing Guide**: [Testing Guide & Failure Matrix](file:///TESTING.md)
* **Reproducing Builds**: [Reproducible Builds Guide](file:///docs/guides/reproduce-build.md)

## Development Doctrine

This repository adheres to the **agent.md project OS doctrine**. Contributions must follow:
* All architecture adjustments require an ADR inside `docs/adr/`.
* Protocol specifications should be mapped as RFCs inside `docs/rfcs/`.
* Code changes must align to the Conventional Commits specification.

---

## License

AnonyMus is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](file:///LICENSE) for details.
