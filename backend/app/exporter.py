import struct
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

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


def multi_object_3mf(parts: list[tuple[str, Mesh]], title: str) -> bytes:
    """Create a geometry-only 3MF containing aligned independent objects.

    There is deliberately no printer, process or filament configuration. A
    slicer may assign one filament to both objects or a different filament to
    each without this file overriding the user's own setup.
    """
    model_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="pl-PL" '
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
        f'  <metadata name="Title">{escape(title)}</metadata>',
        '  <resources>',
    ]

    object_ids: list[int] = []
    for object_index, (name, mesh) in enumerate(parts):
        object_id = object_index + 1
        object_ids.append(object_id)
        model_lines.extend((
            f'    <object id="{object_id}" type="model" name="{escape(name)}">',
            '      <mesh>',
            '        <vertices>',
        ))
        model_lines.extend(
            f'          <vertex x="{float(x):.6f}" y="{float(y):.6f}" z="{float(z):.6f}"/>'
            for x, y, z in mesh.vertices
        )
        model_lines.extend(('        </vertices>', '        <triangles>'))
        model_lines.extend(
            f'          <triangle v1="{int(a)}" v2="{int(b)}" v3="{int(c)}"/>'
            for a, b, c in mesh.faces
        )
        model_lines.extend(('        </triangles>', '      </mesh>', '    </object>'))

    model_lines.extend((
        '  </resources>',
        '  <build>',
        *(f'    <item objectid="{object_id}"/>' for object_id in object_ids),
        '  </build>',
        '</model>',
    ))

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
        '</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        '</Relationships>'
    )
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("3D/3dmodel.model", "\n".join(model_lines))
    return output.getvalue()
