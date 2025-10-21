---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "Magentic Marketplace"
  tagline: Simulation Environment for Agentic Marketplaces
  image:
    alt: Magentic Marketplace Demo
  actions:
    - theme: brand
      text: Get Started
      link: /getting-started/installation
    - theme: alt
      text: Guide
      link: /concepts/overview

features:
  - title: Simulate Agentic Marketplaces
    link: /getting-started/usage/cli
    details: |
      Run experiments with customer and business agents that search, converse, and make transactions
      <img src="./run.png" alt="Run command" style="width: 100%; margin-top: 1rem; border-radius: 12px;" />

  - title: Understand Marketplace Dynamics
    link: /getting-started/usage/cli
    details: |
      Analyze agent behavior with market welfare and understand agent biases and malicious behavior
      <img src="./analyze.png" alt="analyze command" style="width: 100%; margin-top: 1rem; border-radius: 12px;" />
---

<div style="display: flex; justify-content: center; margin-top: 6rem;">
  <div style="position: relative; max-width: 800px; width: 100%;">
    <div style="position: absolute; inset: 0; background: linear-gradient(-45deg, #922185 , #fb81ff ); border-radius: 0px; opacity: 0.5; z-index: -1; filter: blur(44px);"></div>
    <video controls="controls" src="/mm-demo.mp4" style="max-height: 450px; width: 100%; border-radius: 0px;">
    </video>
  </div>
</div>
