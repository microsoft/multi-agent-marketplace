## Magentic Marketplace Repo & Synthetic Data

### Overview

Magentic Marketplace is an open-source environment for studying simulated multi-agentic marketplace scenarios, where AI agents participate in marketplaces with varying degrees of delegated autonomy on behalf of customers and businesses. The environment enables researchers to simulate and assess the welfare of marketplace participants under different conditions and baselines, supporting the full transaction lifecycle from search and discovery to transaction fulfillment.

Magentic Marketplace includes two synthetic datasets for end-to-end agentic marketplace simulations:

- **Mexican Restaurant Dataset:**  
  Contains 100 customer requests and 300 Mexican restaurants across multiple scales (from 3 businesses/9 customers to 100 businesses/300 customers). Each restaurant features a menu of food options with prices, name and location information, and amenity features such as free WiFi, outdoor seating, delivery options, and custom decorations. Menu prices are independently sampled from item-specific distributions to ensure sufficient variation for testing and evaluating agent decision-making under different pricing scenarios.

- **Contractors Dataset:**  
  Contains home contracting services with customer requests and contractor businesses across multiple scales (from 10 businesses/30 customers to 100 businesses/300 customers). Each contractor offers various home improvement services (painting, plumbing, electrical, landscaping, etc.) with realistic pricing distributions, business amenities (licensing, insurance, availability), and service capabilities designed to create scenarios where agents must navigate complex service matching and negotiation processes.

Both datasets are designed to demonstrate the value of two-sided agentic marketplaces, enabling richer interactions between customer and business agents through direct communication, negotiation, and dynamic pricing.

See related [README](./README.md).  

A detailed discussion of the project can be found in our paper at: [TO DO: include Arxiv paper link once live](./README.md)

### What Can Magentic Marketplace Do

Magentic Marketplace was developed to enable researchers and practitioners to safely study how AI agents behave in realistic marketplace environments and design mechanisms that improve their robustness and welfare. The environment provides a comprehensive testing ground for experimental exploration of these trade-offs, revealing how small changes in protocols lead to meaningful outcome differences in agent decision-making, negotiation strategies, market efficiency, and welfare outcomes.

Synthetic datasets are released to enable controlled experiments on critical marketplace design questions without requiring real-world data or live marketplace deployment. These datasets provide realistic scenarios for studying agent biases, vulnerability to manipulation, and search ordering effects.

### Intended Uses

- Studying AI agent behavior in marketplace environments, market mechanism design, and the economics of agentic systems.
- Immediate experimentation with synthetic datasets, without domain-specific data collection.
- Custom dataset integration is possible with adaptation to the platform's format.
- Synthetic data generation scripts are available for creating custom datasets.
- Platform and datasets are shared to facilitate reproduction of results and further research.
- Intended for use by domain experts capable of evaluating output quality.

### Out-of-Scope Uses

- Not suited for production marketplace applications, real-world commercial deployment, or systems requiring high-reliability agent behavior.
- Synthetic datasets are not suitable for training production AI systems, validating real-world business models, or making actual marketplace recommendations.
- Datasets lack complex customer decision factors, dynamic business operations, competitive market pressures, and real-world contextual factors.
- Not expected to generalize well to real-world marketplace outcomes.

## Dataset Details

### Dataset Contents

- **Mexican Restaurant Dataset:**  
  300 businesses and 100 customers. Business profiles include metadata, menu features, amenity features, and minimum price factors. Customer profiles include requests, menu features, and required amenities.

- **Contractors Dataset:**  
  300 businesses and 100 customers. Contractor profiles include business metadata, service offerings, and capability features. Customer profiles include service requests and requirements.

Datasets generated using automated LLM-based scripts (August–September 2025), with structured prompts and validation for realistic scenarios.

### Data Creation & Processing

- Programmatic generation methods leveraging LLMs.
- Automated scripts for menu/service item generation, business profile creation, and customer profile generation.
- Multiple retry mechanisms, consistency checks, and format validation for high-quality synthetic data.

### People & Identifiers

- Data points simulate individual preferences and willingness to pay.
- No correspondence to real people.

### Sensitive or Harmful Content

- Synthetic datasets are not believed to contain offensive or distressing information.

### Other Processing

- Duplicate/redundant information removed via software-based deduplication.
- Annotated with structured marketplace metadata.
- Labeling/annotation performed automatically during generation.

## Getting Started

- Follow README instructions to begin using Magentic Marketplace and synthetic data.

## Validation

Validation scripts verify:

- Business-customer compatibility
- Price consistency
- Feature validation
- Name collision detection
- Statistical validation

## Evaluation

Effectiveness assessed via:

- Log analysis
- Comparative benchmarks
- Robustness checks
- Model diversity

See paper for detailed discussion: [TO DO: add arxiv link](./README.md)

## Limitations

### Code

- Developed for research and experimental purposes.
- Further testing needed for commercial use.
- Designed and tested in English; performance in other languages may vary.
- Outputs may include errors or speculation; human oversight required.
- Inherits biases/errors from base models.
- Not designed to protect from security vulnerabilities.

### Data

- Synthetic datasets for research/experimentation only.
- English language instances only.
- Lack of complex decision factors and real-world contextual features.
- Not systematically evaluated for bias; users should consider and mitigate potential biases.

## Best Practices

- Leverage modular architecture for custom dataset integration.
- Use validation scripts for compatibility.
- Establish baselines and control groups.
- Use multiple dataset scales for validation.
- Configure similarity matching as needed.
- Test robustness across LLM providers.
- Use analytics endpoints for metrics.
- Implement proper logging for reproducibility.
- Scale experiments for statistical validation.
- Employ Responsible AI mitigations (see Azure OpenAI resources).

**Responsible AI Resources:**
- [Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview)
- [Responsible AI practices for Azure OpenAI models](https://learn.microsoft.com/en-us/legal/cognitive-services/openai/overview)
- [Azure OpenAI Transparency Note](https://learn.microsoft.com/en-us/legal/cognitive-services/openai/transparency-note)
- [OpenAI’s Usage policies](https://openai.com/policies/usage-policies)
- [Azure OpenAI’s Code of Conduct](https://learn.microsoft.com/en-us/legal/cognitive-services/openai/code-of-conduct)

- Users must ensure compliance with data protection regulations and organizational guidelines.
- Source datasets legally and ethically.

## License

[MIT License](./LICENSE)

## Trademarks

- Use of Microsoft trademarks/logos must follow Microsoft’s Trademark & Brand Guidelines.
- Third-party trademarks/logos subject to respective policies.

## Ethics

- Synthetic data generation designed to avoid privacy compromise.
- All entities are artificially generated.
- Prompts designed to avoid discriminatory, offensive, or harmful content.

## Contact

Research conducted by members of [Microsoft Research](https://www.microsoft.com/en-us/research/).  
Feedback and collaboration welcome: magenticmarket@microsoft.com  
Repository will be updated with mitigations as needed.
