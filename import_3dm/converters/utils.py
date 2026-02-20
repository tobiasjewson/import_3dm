# MIT License

# Copyright (c) 2018-2024 Nathan Letwory, Joel Putnam, Tom Svilans, Lukas Fertig

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# *** data tagging

import bpy
import uuid
import rhino3dm as r3d
from mathutils import Matrix

from typing import Any, Dict

def tag_data(
        idblock : bpy.types.ID,
        tag_dict: Dict[str, Any]
    )   -> None:
    """
    Given a Blender data idblock tag it with the id an name
    given using custom properties. These are used to track the
    relationship with original Rhino data.
    """
    guid = tag_dict.get('rhid', None)
    name = tag_dict.get('rhname', None)
    matid = tag_dict.get('rhmatid', None)
    parentid = tag_dict.get('rhparentid', None)
    is_idef = tag_dict.get('rhidef', False)
    idblock['rhid'] = str(guid)
    idblock['rhname'] = name
    idblock['rhmatid'] = str(matid)
    idblock['rhparentid'] = str(parentid)
    idblock['rhidef'] = is_idef
    idblock['rhmat_from_object'] = tag_dict.get('rhmat_from_object', True)

def create_tag_dict(
        guid            : uuid.UUID,
        name            : str,
        matid           : uuid.UUID = None,
        parentid        : uuid.UUID = None,
        is_idef         : bool = False,
        mat_from_object : bool = True,
) -> Dict[str, Any]:
    """
    Create a dictionary with the tag data. This can be used
    to pass to the tag_dict and get_or_create_iddata functions.

    guid and name are mandatory.
    """
    return {
        'rhid': guid,
        'rhname': name,
        'rhmatid': matid,
        'rhparentid': parentid,
        'rhidef': is_idef,
        'rhmat_from_object': mat_from_object
    }

all_dict = dict()

def clear_all_dict() -> None:
    global all_dict
    all_dict = dict()

def reset_all_dict(context : bpy.types.Context) -> None:
    global all_dict
    all_dict = dict()
    bases = [
        context.blend_data.objects,
        context.blend_data.cameras,
        context.blend_data.lights,
        context.blend_data.meshes,
        context.blend_data.materials,
        context.blend_data.collections,
        context.blend_data.curves
    ]
    for base in bases:
        t = repr(base).split(',')[1]
        if t in all_dict:
            dct = all_dict[t]
        else:
            dct = dict()
            all_dict[t] = dct
        for item in base:
            rhid = item.get('rhid', None)
            if rhid:
                dct[rhid] = item

def get_dict_for_base(base : bpy.types.bpy_prop_collection) -> Dict[str, bpy.types.ID]:
    global all_dict
    t = repr(base).split(',')[1]
    if t not in all_dict:
        pass
    return all_dict[t]

def get_or_create_iddata(
        base    : bpy.types.bpy_prop_collection,
        tag_dict: Dict[str, Any],
        obdata : bpy.types.ID,
        use_none : bool = False
    )   -> bpy.types.ID:
    """
    Get an iddata.
    The tag_dict collection should contain a guid if the goal
    is to find an existing item. If an object with given guid is found in
    this .blend use that. Otherwise new up one with base.new,
    potentially with obdata if that is set

    If obdata is given then the found object data will be set
    to that.
    """
    founditem : bpy.types.ID = None
    guid = tag_dict.get('rhid', None)
    name = tag_dict.get('rhname', None)
    matid = tag_dict.get('rhmatid', None)
    parentid = tag_dict.get('rhparentid', None)
    is_idef = tag_dict.get('rhidef', False)
    dct = get_dict_for_base(base)
    if guid is not None:
        strguid = str(guid)
        if strguid in dct:
            founditem = dct[strguid]
    if founditem:
        theitem = founditem
        theitem['rhname'] = name
        if obdata and type(theitem) != type(obdata):
            theitem.data = obdata
    else:
        if obdata or use_none:
            theitem = base.new(name=name, object_data=obdata)
        else:
            theitem = base.new(name=name)
        if guid is not None:
            strguid = str(guid)
            dct[strguid] = theitem
        tag_data(theitem, tag_dict)
    return theitem

def _collect_valid_guids(model):
    """Build a set of all valid GUIDs from the .3dm model."""
    valid = set()

    for ob in model.Objects:
        valid.add(str(ob.Attributes.Id))

    for layer in model.Layers:
        valid.add(str(layer.Id))

    for mat in model.Materials:
        valid.add(str(mat.Id))
        rc = model.RenderContent.FindId(mat.RenderMaterialInstanceId)
        if rc:
            valid.add(str(mat.RenderMaterialInstanceId))

    for idef in model.InstanceDefinitions:
        valid.add(str(idef.Id))

    # Default material GUIDs (from material.py)
    valid.add("00000000-abcd-ef01-2345-000000000000")
    valid.add("00000000-abcd-ef01-6789-000000000000")

    return valid


def remove_stale_data(context, model):
    """Remove Blender data whose Rhino GUID is no longer in the .3dm file."""
    valid_guids = _collect_valid_guids(model)

    # Collect set of rhids that survive (for annotation child check)
    surviving_rhids = set()
    for ob in context.blend_data.objects:
        rhid = ob.get("rhid", None)
        if rhid and rhid != "None" and rhid in valid_guids:
            surviving_rhids.add(rhid)

    # 1. Remove stale objects
    objects_to_remove = []
    for ob in context.blend_data.objects:
        rhid = ob.get("rhid", None)
        if rhid is None or rhid == "None":
            continue
        if rhid in valid_guids:
            continue
        # Skip annotation text children whose parent annotation still exists.
        # These have rhname starting with "TXT" (set in converters/__init__.py).
        if (ob.get("rhname", "").startswith("TXT")
                and ob.parent
                and ob.parent.get("rhid", None) in surviving_rhids):
            continue
        objects_to_remove.append(ob)

    for ob in objects_to_remove:
        data = ob.data
        for col in ob.users_collection:
            col.objects.unlink(ob)
        context.blend_data.objects.remove(ob)
        # Remove orphaned data blocks
        if data and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                context.blend_data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                context.blend_data.curves.remove(data)
            elif isinstance(data, bpy.types.Camera):
                context.blend_data.cameras.remove(data)
            elif isinstance(data, bpy.types.Light):
                context.blend_data.lights.remove(data)

    # 2. Remove stale collections
    collections_to_remove = []
    for col in context.blend_data.collections:
        rhid = col.get("rhid", None)
        if rhid is None or rhid == "None":
            continue
        if rhid not in valid_guids:
            collections_to_remove.append(col)

    for col in collections_to_remove:
        context.blend_data.collections.remove(col)

    # 3. Remove stale materials
    materials_to_remove = []
    for mat in context.blend_data.materials:
        rhid = mat.get("rhid", None)
        if rhid is None or rhid == "None":
            continue
        if rhid not in valid_guids:
            materials_to_remove.append(mat)

    for mat in materials_to_remove:
        context.blend_data.materials.remove(mat)


def matrix_from_xform(xform : r3d.Transform):
     m = Matrix(
            ((xform.M00, xform.M01, xform.M02, xform.M03),
            (xform.M10, xform.M11, xform.M12, xform.M13),
            (xform.M20, xform.M21, xform.M22, xform.M23),
            (xform.M30, xform.M31, xform.M32, xform.M33))
     )
     return m