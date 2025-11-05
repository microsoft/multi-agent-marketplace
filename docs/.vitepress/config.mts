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
    base: "/multi-agent-marketplace/",
    title: "Magentic Marketplace",
    description: "Simulate Agentic Markets and See How They Evolve",
    head: [["link", { rel: "icon", href: "/logo.svg" }]],
    markdown: {
      theme: customTheme,
    },
    themeConfig: {
      // https://vitepress.dev/reference/default-theme-config
      logo: "/logo.svg",
      siteTitle: false,

      nav: [
        { text: "Home", link: "/" },
        { text: "Getting Started", link: "/usage/installation" },
        { text: "Guide", link: "/concepts/overview" },
      ],

      sidebar: [
        {
          text: "Introduction",
          items: [
            {
              text: "Quick Start & Install",
              link: "/usage/installation",
            },
            {
              text: "Environment Setup",
              link: "/usage/env",
            },
            {
              text: "CLI",
              collapsed: true,
              items: [
                { text: "Overview", link: "/usage/cli-intro" },
                { text: "Run", link: "/usage/cli-run" },
                { text: "Analyze", link: "/usage/cli-analyze" },
                { text: "Export", link: "/usage/cli-export" },
                { text: "List", link: "/usage/cli-list" },
                { text: "UI", link: "/usage/cli-ui" },
              ],
            },
            { text: "Python API", link: "/usage/python" },
          ],
        },
        {
          text: "Core Concepts",
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
    ignoreDeadLinks: true,
  })
);
