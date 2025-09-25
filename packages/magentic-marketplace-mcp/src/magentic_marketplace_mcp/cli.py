"""Main entry point for running the MCP server."""

import argparse
import asyncio
import importlib
import logging

logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    logger.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(description="MCP Server for Magentic Marketplace")
    parser.add_argument(
        "--marketplace-url",
        type=str,
        required=True,
        help="URL of the marketplace server",
    )
    parser.add_argument(
        "--agent-profile",
        type=str,
        help="Path to a .json file containing an AgentProfile",
    )
    parser.add_argument(
        "--agent-profile-type",
        type=str,
        default="magentic_marketplace.platform.shared.models.AgentProfile",
    )
    parser.add_argument(
        "--agent-id", type=str, help="Agent ID if no agent-profile is provided."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level (default: INFO)",
    )
    args = parser.parse_args()
    logger.info(
        f"Parsed arguments: marketplace_url={args.marketplace_url}, agent_profile={args.agent_profile}, agent_id={args.agent_id}, log_level={args.log_level}"
    )
    return args


async def amain():
    """Run the MCP server."""
    args = parse_args()

    # Update logging level based on CLI args
    if hasattr(args, "log_level"):
        log_level = getattr(logging, args.log_level)
        logging.getLogger().setLevel(log_level)
        for handler in logging.getLogger().handlers:
            handler.setLevel(log_level)
        logger.debug(f"Updated logging level to {args.log_level}")

    logger.info("Starting MCP server")

    # Defer imports until after cli args are validated
    logger.debug("Importing required modules")
    from magentic_marketplace.platform.shared.models import AgentProfile

    from .server import MarketplaceMCPServer

    if args.agent_profile:
        logger.info(f"Loading agent profile from: {args.agent_profile}")
        module_name, class_name = args.agent_profile_type.rsplit(".", 1)
        logger.debug(f"Importing module {module_name} and class {class_name}")
        module = importlib.import_module(module_name)
        agent_type = getattr(module, class_name)
        if not issubclass(agent_type, AgentProfile):
            logger.error(f"{args.agent_profile_type} is not a subclass of AgentProfile")
            raise TypeError(
                f"{args.agent_profile_type} is not a subclass of AgentProfile"
            )

        if args.agent_profile[0] == "{":
            logger.debug("Agent profile provided as JSON string")
            agent_profile_data = args.agent_profile
        else:
            logger.debug(f"Reading agent profile from file: {args.agent_profile}")
            try:
                with open(args.agent_profile) as fd:
                    agent_profile_data = fd.read()
            except FileNotFoundError:
                logger.error(f"Agent profile file not found: {args.agent_profile}")
                raise
            except PermissionError:
                logger.error(
                    f"Permission denied reading agent profile file: {args.agent_profile}"
                )
                raise
            except Exception as e:
                logger.exception(
                    f"Failed to read agent profile file {args.agent_profile}: {e}"
                )
                raise

        try:
            agent_profile = agent_type.model_validate_json(agent_profile_data)
            logger.info(
                f"Successfully loaded agent profile with ID: {agent_profile.id}"
            )
        except Exception as e:
            logger.exception(f"Failed to parse agent profile JSON: {e}")
            raise
    elif args.agent_id:
        logger.info(f"Creating agent profile with ID: {args.agent_id}")
        agent_profile = AgentProfile(id=args.agent_id)
    else:
        logger.error("One of --agent-profile or --agent-id is required")
        raise ValueError("One of --agent-profile or --agent-id is required.")

    # Create and run the MCP server
    logger.info(f"Creating MCP server for marketplace: {args.marketplace_url}")
    server = MarketplaceMCPServer(agent_profile, args.marketplace_url)
    logger.info("Starting MCP server over stdio")
    logger.info("Server will now wait for MCP client connection over stdio...")
    try:
        await server.run_stdio()
    except Exception as e:
        logger.exception(f"MCP server failed during execution: {e}")
        raise


def main():
    """Run the MCP server."""
    # Set up basic logging first
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: [%(name)s] (%(asctime)s) %(message)s"
    )
    logger.info("Initializing MCP server application")

    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        logger.warning("Received interrupt signal, shutting down gracefully")
        raise
    except SystemExit:
        logger.info("Application exiting")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during MCP server execution: {e}")
        raise


if __name__ == "__main__":
    main()
