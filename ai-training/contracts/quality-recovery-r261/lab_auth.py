"""Pure lab account routing and URI100 projection, no capture-runner imports."""


def login_username(oracle):
    if oracle == "login-admin":
        return "labu1"
    if oracle == "login-student":
        return "labu2"
    raise ValueError("Unknown lab login role")


def stage_guest_python(source, root, relative):
    """Replace only the explicit private guest staging file, never a host file."""
    target = root / relative.lstrip("/")
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Unsafe guest staging path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    target.chmod(0o600)
    return target


def uri100(target, method):
    import numpy as np
    from r23_features import describe_lane, sketch

    from idps_ai.features.request_time import from_request

    path, query = sketch(target)
    shape = (
        np.minimum(31, describe_lane(path, b"/") + describe_lane(query, b"&")).astype(np.float32)
        / 31
    )
    return np.r_[from_request(target, method), shape].astype(np.float32)
