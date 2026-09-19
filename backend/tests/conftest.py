import os


# Existing generator tests exercise their own contracts. Authentication has a
# dedicated suite and is enabled by default in every real deployment.
os.environ["LITHO_AUTH_DISABLED"] = "true"
os.environ["LITHO_SECURE_COOKIES"] = "false"
