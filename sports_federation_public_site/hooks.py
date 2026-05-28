def post_init_hook(env):
    """Run the module post-init hook."""
    env["website"]._cleanup_default_public_site_content()
