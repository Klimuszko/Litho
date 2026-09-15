import struct

import numpy as np

from .mesh import Mesh


def binary_stl(mesh: Mesh) -> bytes:
    triangles = mesh.vertices[mesh.faces].astype("<f4")
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals = normals / lengths[:, None]
    record = np.zeros(len(triangles), dtype=[("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    record["normal"] = normals
    record["vertices"] = triangles
    header = b"Lithophane Generator V1".ljust(80, b"\0")
    return header + struct.pack("<I", len(record)) + record.tobytes()
