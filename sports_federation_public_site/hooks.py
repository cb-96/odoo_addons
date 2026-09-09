def post_init_hook(env):
    """Leave stock website records intact during module installation.

    Federation navigation is installed through module XML. Destructive cleanup
    remains available as an explicit operator action, but running it globally
    during installation contaminates Odoo website tests and unrelated websites.
    """
    return True
