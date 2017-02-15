import os
import bpy
from bpy.props import BoolProperty, IntProperty

from .functions.global_settings import ProjectSettings, Extensions
from .functions.file_management import *
from .functions.animation import add_transform_effect
from .functions.sequences import find_empty_channel


# TODO: auto process img strips - add transform that scales it down to its original size
# and sets blend mode to alpha_over
class ImportLocalFootage(bpy.types.Operator):
    bl_idname = "gdquest_vse.import_local_footage"
    bl_label = "Import local footage"
    bl_description = "Import video and audio from the project folder to VSE strips"
    bl_options = {'REGISTER', 'UNDO'}

    import_all = BoolProperty(
        name="Always Reimport",
        description="If true, always import all local files to new strips. \
                    If False, only import new files (check if footage has \
                    already been imported to the VSE).",
        default=False)
    keep_audio = BoolProperty(
        name="Keep audio from video files",
        description=
        "If False, the audio that comes with video files will not be imported",
        default=True)

    img_length = IntProperty(
        name="Image strip length",
        description=
        "Controls the duration of the imported image strips length",
        default=96,
        min=1)
    img_padding = IntProperty(
        name="Image strip padding",
        description="Padding added between imported image strips in frames",
        default=24,
        min=1)

    # PSD related features
    # import_psd = BoolProperty(
    #     name="Import PSD as image",
    #     description="When True, psd files will be imported as individual image strips",
    #     default=False)
    # ps_assets_as_img = BoolProperty(
    #     name="Import PS assets as images",
    #     description="Imports the content of folders generated by Photoshop's quick export \
    #                 function as individual image strips",
    #     default=True)

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        if not bpy.data.is_saved:
            self.report(
                {"ERROR_INVALID_INPUT"
                 }, "You need to save your project first. Import cancelled.")
            return {"CANCELLED"}

        sequencer = bpy.ops.sequencer
        context = bpy.context
        path = bpy.data.filepath

        bpy.ops.screen.animation_cancel(restore_frame=True)

        wm = bpy.context.window_manager
        SEQUENCER_AREA = {'region': wm.windows[0].screen.areas[2].regions[0],
                          'blend_data': bpy.context.blend_data,
                          'scene': bpy.context.scene,
                          'window': wm.windows[0],
                          'screen': bpy.data.screens['Video Editing'],
                          'area': bpy.data.screens['Video Editing'].areas[2]}

        # Empty channel
        channel_for_audio = 1 if self.keep_audio else 0
        empty_channel = find_empty_channel(mode='ABOVE')
        created_img_strips = []

        directory = get_working_directory(path)
        folders, files, files_dict = {}, {}, {}

        file_types = "AUDIO", "IMG", "VIDEO"

        for folder in os.listdir(path=directory):
            folder_upper = folder.upper()
            if folder_upper in file_types:
                folders[folder_upper] = directory + "\\" + folder

        for name in file_types:
            walk_folders = True if name == "IMG" else False
            files[name] = find_files(folders[name],
                                     Extensions.DICT[name],
                                     recursive=walk_folders)
        # for name in files:
        #     print(name + ":" + str(files[name]))
# Write the list of imported files for each folder to a text file
# Check if text exists. If not, create the files
        TEXT_FILE_PREFIX = 'IMPORT_'
        texts = bpy.data.texts
        import_files = {}
        for name in file_types:
            if texts.get(TEXT_FILE_PREFIX + name):
                import_files[name] = texts[TEXT_FILE_PREFIX + name]

        if not import_files:
            from .functions.file_management import create_text_file
            for name in file_types:
                import_files[name] = create_text_file(TEXT_FILE_PREFIX + name)
            assert len(import_files) == 3

# Write new imported paths to the text files and import new strips
        for name in file_types:
            text_file_content = [
                line.body
                for line in bpy.data.texts[TEXT_FILE_PREFIX + name].lines
            ]
            new_paths = [path
                         for path in files[name]
                         if path not in text_file_content]
            for line in new_paths:
                bpy.data.texts[TEXT_FILE_PREFIX + name].write(line + "\n")

            if not new_paths:
                continue

            folder = folders[name]
            files_dict = files_to_dict(new_paths, folder)
            if name == "VIDEO":
                sequencer.movie_strip_add(SEQUENCER_AREA,
                                          filepath=folder + "\\",
                                          files=files_dict,
                                          frame_start=1,
                                          channel=empty_channel,
                                          sound=self.keep_audio)
            elif name == "AUDIO":
                sequencer.sound_strip_add(SEQUENCER_AREA,
                                          filepath=folder + "\\",
                                          files=files_dict,
                                          frame_start=1,
                                          channel=empty_channel + 2)
            elif name == "IMG":
                img_frame = 1
                for img in files_dict:
                    sequencer.image_strip_add(
                        SEQUENCER_AREA,
                        directory=folder,
                        files=[img],
                        frame_start=img_frame,
                        frame_end=img_frame + self.img_length,
                        channel=empty_channel + 3)
                    img_frame += self.img_length + self.img_padding

                    img_strips = bpy.context.selected_sequences
                    # TODO: img crop and offset to make anim easier
                    # set_img_strip_offset(img_strips)
                    add_transform_effect(img_strips)
        return {"FINISHED"}


def get_working_directory(path=None):
    if not path:
        return None

    project_name = bpy.path.basename(path)
    directory = path[:len(path) - (len(project_name) + 1)]
    return directory


# TODO: Ignore the blender proxy folders
def find_files(directory,
               file_extensions,
               recursive=False,
               ignore_folders=('_proxy')):
    """Walks through a folder and returns a list of filepaths that match the extensions."""
    if not directory and file_extensions:
        return None

    files = []

    from glob import glob
    from os.path import basename

    # TODO: Folder containing img files = img sequence
    for ext in file_extensions:
        source_pattern = directory + "\\"
        pattern = source_pattern + ext
        files.extend(glob(pattern))
        if not recursive:
            continue
        pattern = source_pattern + "**\\" + ext
        files.extend(glob(pattern))

    if basename(directory) == "IMG":
        psd_names = [f for f in glob(directory + "\\*.psd")]
        for i, name in enumerate(psd_names):
            psd_names[i] = name[len(directory):-4]

        psd_folders = (f for f in os.listdir(directory) if f in psd_names)
        for f in psd_folders:
            for ext in file_extensions:
                files.extend(glob(directory + "\\" + f + "\\" + ext))
    return files


def files_to_dict(files, folder_path):
    """Converts a list of files to Blender's dictionary format for import
       Returns a list of dictionaries with the {'name': filename} format
       Args:
        - files: a list or a tuple of files
        - folder_path: a string of the path to the files' containing folder"""
    if not files and folder_path:
        return None

    dictionary = []
    for f in files:
        dict_form = {'name': f[len(folder_path) + 1:]}
        dictionary.append(dict_form)
    return dictionary


def add_strip_from_file(filetype,
                        directory,
                        files,
                        start,
                        end,
                        channel,
                        keep_audio=False):
    """Add a file or a list of files as a strip to the VSE"""
    sequencer = bpy.ops.sequencer
    wm = bpy.context.window_manager
    sequencer_area = {'region': wm.windows[0].screen.areas[2].regions[0],
                      'blend_data': bpy.context.blend_data,
                      'scene': bpy.context.scene,
                      'window': wm.windows[0],
                      'screen': bpy.data.screens['Video Editing'],
                      'area': bpy.data.screens['Video Editing'].areas[2]}

    if filetype == FileTypes.img:
        sequencer.image_strip_add(sequencer_area,
                                  directory=directory,
                                  files=files,
                                  frame_start=start,
                                  frame_end=end,
                                  channel=channel)
    elif filetype == FileTypes.video:
        sequencer.movie_strip_add(sequencer_area,
                                  filepath=directory,
                                  files=files,
                                  frame_start=start,
                                  channel=channel,
                                  sound=keep_audio)
    elif filetype == FileTypes.audio:
        sequencer.sound_strip_add(sequencer_area,
                                  filepath=directory,
                                  frame_start=start,
                                  channel=channel)

    return "SUCCESS"


# FIXME: Currently not getting image width and height (set to 0)
def add_transform_effect(sequences=None):
    """Takes a list of image strips and adds a transform effect to them.
       Ensures that the pivot will be centered on the image"""
    sequencer = bpy.ops.sequencer
    sequence_editor = bpy.context.scene.sequence_editor
    render = bpy.context.scene.render

    sequences = [s for s in sequences if s.type in ('IMAGE', 'MOVIE')]

    if not sequences:
        return None

    sequencer.select_all(action='DESELECT')

    for s in sequences:
        s.mute = True

        sequence_editor.active_strip = s
        sequencer.effect_strip_add(type='TRANSFORM')

        active = sequence_editor.active_strip
        active.name = "TRANSFORM-%s" % s.name
        active.blend_type = 'ALPHA_OVER'
        active.select = False

    print("Successfully processed " + str(len(sequences)) + " image sequences")
    return True

# def calc_transform_effect_scale(sequence):
#     """Takes a transform effect and returns the scale it should use
#        to preserve the scale of its cropped input"""
#     # if not (sequence or sequence.type == 'TRANSFORM'):
#     #     raise AttributeError

#     s = sequence.input_1

#     crop_x, crop_y = s.elements[0].orig_width - (s.crop.min_x + s.crop.max_x),
#                      s.elements[0].orig_height - (s.crop.min_y + s.crop.max_y)
#     ratio_x, ratio_y = crop_x / render.resolution_x,
#                        crop_y / render.resolution_y
#     if ratio_x > 1 or ratio_y > 1:
#         ratio_x /= ratio_y
#         ratio_y /= ratio_x
#     return ratio_x, ratio_y
#     active.scale_start_x, active.scale_start_y = ratio_x ratio_y


# TODO: make it work
def set_img_strip_offset(sequences):
    """Takes a list of img sequences and changes their parameters"""
    if not sequences:
        raise AttributeError('No sequences passed to the function')

    for s in sequences:
        if s.use_translation and (s.offset_x != 0 or s.offset_y != 0):
            continue

        image_width = s.elements[0].orig_width
        image_height = s.elements[0].orig_height

        if image_width == 0 or image_height == 0:
            continue

        res_x, res_y = render.resolution_x, render.resolution_y

        if image_width < res_x or image_height < res_y:
            s.use_translation = True
            s.transform.offset_x = (res_x - image_width) / 2
            s.transform.offset_y = (res_y - image_height) / 2
    return True
