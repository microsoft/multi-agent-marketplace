import { defineConfig } from "vitepress";
import { createCssVariablesTheme } from "shiki";
import { withMermaid } from "vitepress-plugin-mermaid";

const customTheme = createCssVariablesTheme({
  name: "css-variables",
  variablePrefix: "--shiki-",
  variableDefaults: {},
  fontStyle: true,
});

// https://vitepress.dev/reference/site-config
export default withMermaid(
  defineConfig({
    title: "Magentic Marketplace",
    description: "Simulate Agentic Markets and See How They Evolve",
    head: [["link", { rel: "icon", href: "/logo.svg" }]],
    markdown: {
      theme: customTheme,
    },
    themeConfig: {
      // https://vitepress.dev/reference/default-theme-config
      logo: "/logo.svg",

      nav: [
        { text: "Home", link: "/" },
        { text: "Getting Started", link: "/getting-started/installation" },
        { text: "Guide", link: "/concepts/overview" },
      ],

      sidebar: [
        {
          text: "Introduction",
          collapsed: false,

          items: [
            {
              text: "Quick Start & Install",
              link: "/getting-started/installation",
            },
            {
              text: "Usage",
              items: [
                {
                  text: "Environment Setup",
                  link: "/getting-started/usage/env",
                },
                { text: "CLI", link: "/getting-started/usage/cli" },
                { text: "Python API", link: "/getting-started/usage/python" },
              ],
            },
          ],
        },
        {
          text: "Core Concepts",
          collapsed: false,

          items: [
            { text: "Overview", link: "/concepts/overview" },
            { text: "Platform", link: "/concepts/platform" },
            {
              text: "Marketplace Protocol",
              link: "/concepts/marketplace-protocol",
            },
            { text: "Agents", link: "/concepts/agents" },
            { text: "Experiment Data", link: "/concepts/experiment-data" },
          ],
        },
      ],

      socialLinks: [
        {
          icon: "github",
          link: "https://github.com/microsoft/multi-agent-marketplace",
        },
      ],
      search: {
        provider: "local",
      },
    },
  })
);
