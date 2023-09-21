import adsk.core, adsk.fusion, traceback
import os
import math
import json
from dataclasses import asdict

from ...lib import configUtils
from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import geometryUtils
from ...lib.gridfinityUtils import faceUtils
from ...lib.gridfinityUtils import shellUtils
from ...lib.gridfinityUtils import const
from ...lib.gridfinityUtils.baseGenerator import createGridfinityBase
from ...lib.gridfinityUtils.baseGeneratorInput import BaseGeneratorInput
from ...lib.gridfinityUtils.binBodyGenerator import createGridfinityBinBody, uniformCompartments
from ...lib.gridfinityUtils.binBodyGeneratorInput import BinBodyGeneratorInput, BinBodyCompartmentDefinition
from .inputState import InputState
from .staticInputCache import StaticInputCache

app = adsk.core.Application.get()
ui = app.userInterface


# TODO *** Specify the command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdLid'
CMD_NAME = 'Gridfinity lid'
CMD_Description = 'Create simple gridfinity lid'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# TODO *** Define the location where the command button will be created. ***
# This is done by specifying the workspace, the tab, and the panel, and the
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

CONFIG_FOLDER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'commandConfig')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Constants
BIN_BASIC_SIZES_GROUP = "bin_basic_sizes_group"
BIN_DIMENSIONS_GROUP = "bin_dimensions_group"
BIN_FEATURES_GROUP = "bin_features_group"
BIN_BASE_FEATURES_GROUP_ID = 'bin_base_features_group'
USER_CHANGES_GROUP_ID = 'user_changes_group'
PREVIEW_GROUP_ID = 'preview_group'

BIN_BASE_WIDTH_UNIT_INPUT_ID = 'base_width_unit'
BIN_BASE_LENGTH_UNIT_INPUT_ID = 'base_length_unit'
BIN_HEIGHT_UNIT_INPUT_ID = 'height_unit'
BIN_XY_TOLERANCE_INPUT_ID = 'bin_xy_tolerance'
BIN_WIDTH_INPUT_ID = 'bin_width'
BIN_LENGTH_INPUT_ID = 'bin_length'
BIN_HEIGHT_INPUT_ID = 'bin_height'
BIN_WIDTH_INPUT_ID = 'bin_width'
BIN_REAL_DIMENSIONS_TABLE = "real_dimensions"
BIN_WALL_THICKNESS_INPUT_ID = 'bin_wall_thickness'
BIN_GENERATE_BASE_INPUT_ID = 'bin_generate_base'
BIN_GENERATE_BODY_INPUT_ID = 'bin_generate_body'
BIN_SCREW_HOLES_INPUT_ID = 'bin_screw_holes'
BIN_MAGNET_CUTOUTS_INPUT_ID = 'bin_magnet_cutouts'
BIN_SCREW_DIAMETER_INPUT = 'screw_diameter'
BIN_MAGNET_DIAMETER_INPUT = 'magnet_diameter'
BIN_MAGNET_HEIGHT_INPUT = 'magnet_height'
BIN_WITH_LIP_INPUT_ID = 'with_lip'
BIN_WITH_LIP_NOTCHES_INPUT_ID = 'with_lip_notches'
BIN_TYPE_DROPDOWN_ID = 'bin_type'
BIN_TYPE_HOLLOW = 'Hollow'
BIN_TYPE_SHELLED = 'Shelled'
BIN_TYPE_SOLID = 'Solid'

PRESERVE_CHAGES_RADIO_GROUP = 'preserve_changes'
PRESERVE_CHAGES_RADIO_GROUP_PRESERVE = 'Preserve inputs'
PRESERVE_CHAGES_RADIO_GROUP_RESET = 'Reset inputs after creation'
RESET_CHAGES_INPUT = 'reset_changes'
SHOW_PREVIEW_INPUT = 'show_preview'
SHOW_PREVIEW_MANUAL_INPUT = 'show_preview_manual'

def defaultUiState():
    return InputState(
        groups={},
        baseWidth=const.DIMENSION_DEFAULT_WIDTH_UNIT,
        baseLength=const.DIMENSION_DEFAULT_WIDTH_UNIT,
        heightUnit=const.DIMENSION_DEFAULT_HEIGHT_UNIT,
        xyTolerance=const.BIN_XY_TOLERANCE,
        binWidth=2,
        binLength=3,
        binHeight=1,
        hasBody=True,
        binBodyType=BIN_TYPE_SOLID,
        binWallThickness=const.BIN_WALL_THICKNESS,
        hasLip=True,
        hasLipNotches=True,
        hasBase=True,
        hasBaseScrewHole=False,
        baseScrewHoleSize=const.DIMENSION_SCREW_HOLE_DIAMETER,
        hasBaseMagnetSockets=False,
        baseMagnetSocketSize=const.DIMENSION_MAGNET_CUTOUT_DIAMETER,
        baseMagnetSocketDepth=const.DIMENSION_MAGNET_CUTOUT_DEPTH,
        preserveChanges=False,
    )

uiState = defaultUiState()
staticInputCache = StaticInputCache()

# json.dumps(asdict(uiState))

def getErrorMessage():
    stackTrace = traceback.format_exc();
    return f"An unknonwn error occurred, please validate your inputs and try again:\n{stackTrace}"

def showErrorInMessageBox():
    if ui:
        ui.messageBox(getErrorMessage(), f"{CMD_NAME} Error")

# Executed when add-in is run.
def start():
    addinConfig = configUtils.readConfig(CONFIG_FOLDER_PATH)

    # Create a command Definition.
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******** Add a button into the UI so the user can run the command. ********
    # Get the target workspace the button will be created in.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get the panel the button will be created in.
    panel = workspace.toolbarPanels.itemById(PANEL_ID)

    # Create the button command control in the UI after the specified existing command.
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

    # Specify if the command is promoted to the main toolbar.
    control.isPromoted = addinConfig['UI'].getboolean('is_promoted')

# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control: adsk.core.CommandControl = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    addinConfig = configUtils.readConfig(CONFIG_FOLDER_PATH)
    addinConfig['UI']['is_promoted'] = 'yes' if command_control.isPromoted else 'no'
    configUtils.writeConfig(addinConfig, CONFIG_FOLDER_PATH)


    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

def render_actual_bin_dimensions_table(inputs: adsk.core.CommandInputs):
    actualDimensionsTable = inputs.addTableCommandInput(BIN_REAL_DIMENSIONS_TABLE, "Actual dimensions (mm)", 3, "1:1:1")
    totalWidth = actualDimensionsTable.commandInputs.addStringValueInput("total_real_width", "", "Total width")
    totalWidth.isReadOnly = True
    totalLength = actualDimensionsTable.commandInputs.addStringValueInput("total_real_length", "", "Total length")
    totalLength.isReadOnly = True
    totalHeight = actualDimensionsTable.commandInputs.addStringValueInput("total_real_height", "", "Total height")
    totalHeight.isReadOnly = True
    actualDimensionsTable.addCommandInput(totalWidth, 0, 0)
    actualDimensionsTable.addCommandInput(totalLength, 0, 1)
    actualDimensionsTable.addCommandInput(totalHeight, 0, 2)
    actualDimensionsTable.tablePresentationStyle = adsk.core.TablePresentationStyles.transparentBackgroundTablePresentationStyle
    actualDimensionsTable.hasGrid = False
    actualDimensionsTable.minimumVisibleRows = 1
    actualDimensionsTable.maximumVisibleRows = 1
    return actualDimensionsTable

def formatString(text: str, color: str=""):
    if len(color) > 0:
        return f"<p style='color:{color}'>{text}</p>"
    return text

def update_actual_bin_dimensions(actualBinDimensionsTable: adsk.core.TableCommandInput, width: adsk.core.ValueInput, length: adsk.core.ValueInput, heigh: adsk.core.ValueInput):
    try:
        totalWidth: adsk.core.StringValueCommandInput = actualBinDimensionsTable.getInputAtPosition(0, 0)
        totalWidth.value = "Total width: {}mm".format(round(width.realValue * 10, 2))
        totalLength: adsk.core.StringValueCommandInput = actualBinDimensionsTable.getInputAtPosition(0, 1)
        totalLength.value = "Total length: {}mm".format(round(length.realValue * 10, 2))
        totalHeight: adsk.core.StringValueCommandInput = actualBinDimensionsTable.getInputAtPosition(0, 2)
        totalHeight.value = "Total height: {}mm".format(round(heigh.realValue * 10, 2))
    except:
        showErrorInMessageBox()

def is_all_input_valid(inputs: adsk.core.CommandInputs):
    result = True
    base_width_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_WIDTH_UNIT_INPUT_ID)
    base_length_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_LENGTH_UNIT_INPUT_ID)

    height_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_UNIT_INPUT_ID)
    xy_tolerance: adsk.core.ValueCommandInput = inputs.itemById(BIN_XY_TOLERANCE_INPUT_ID)
    bin_width: adsk.core.ValueCommandInput = inputs.itemById(BIN_WIDTH_INPUT_ID)
    bin_length: adsk.core.ValueCommandInput = inputs.itemById(BIN_LENGTH_INPUT_ID)
    bin_height: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_INPUT_ID)
    bin_wall_thickness: adsk.core.ValueCommandInput = inputs.itemById(BIN_WALL_THICKNESS_INPUT_ID)
    bin_screw_holes: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_SCREW_HOLES_INPUT_ID)
    bin_magnet_cutouts: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_MAGNET_CUTOUTS_INPUT_ID)
    bin_generate_base: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BASE_INPUT_ID)
    bin_generate_body: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BODY_INPUT_ID)
    bin_screw_hole_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCREW_DIAMETER_INPUT)
    bin_magnet_cutout_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_DIAMETER_INPUT)
    bin_magnet_cutout_depth: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_HEIGHT_INPUT)
    with_lip: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_INPUT_ID)
    with_lip_notches: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_NOTCHES_INPUT_ID)
    binTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_TYPE_DROPDOWN_ID)

    result = result and base_width_unit.value > 1
    result = result and base_length_unit.value > 1
    result = result and height_unit.value > 0.5
    result = result and xy_tolerance.value >= 0.01 and xy_tolerance.value <= 0.05
    result = result and bin_width.value > 0
    result = result and bin_length.value > 0
    result = result and bin_height.value >= 1
    result = result and bin_wall_thickness.value >= 0.04 and bin_wall_thickness.value <= 0.2
    if bin_generate_base.value:
        result = result and (not bin_screw_holes.value or bin_screw_hole_diameter.value > 0.1) and (not bin_magnet_cutouts.value or bin_screw_hole_diameter.value < bin_magnet_cutout_diameter.value)
        result = result and bin_magnet_cutout_depth.value > 0

    return result

# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')

    args.command.setDialogInitialSize(400, 500)

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = app.activeProduct.unitsManager.defaultLengthUnits
    basicSizesGroup = inputs.addGroupCommandInput(BIN_BASIC_SIZES_GROUP, 'Basic sizes')
    basicSizesGroup.isExpanded = uiState.getGroupExpandedState(BIN_BASIC_SIZES_GROUP)
    baseWidthUnitInput = basicSizesGroup.children.addValueInput(BIN_BASE_WIDTH_UNIT_INPUT_ID, 'Base width unit (mm)', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.baseWidth))
    baseWidthUnitInput.minimumValue = 1
    baseWidthUnitInput.isMinimumInclusive = True
    baseLengthUnitInput = basicSizesGroup.children.addValueInput(BIN_BASE_LENGTH_UNIT_INPUT_ID, 'Base length unit (mm)', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.baseLength))
    baseLengthUnitInput.minimumValue = 1
    baseLengthUnitInput.isMinimumInclusive = True
    binHeightUnitInput = basicSizesGroup.children.addValueInput(BIN_HEIGHT_UNIT_INPUT_ID, 'Bin height unit (mm)', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.heightUnit))
    binHeightUnitInput.minimumValue = 0.5
    binHeightUnitInput.isMinimumInclusive = True
    xyClearanceInput = basicSizesGroup.children.addValueInput(BIN_XY_TOLERANCE_INPUT_ID, 'Bin xy tolerance (mm)', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.xyTolerance))
    xyClearanceInput.minimumValue = 0.01
    xyClearanceInput.isMinimumInclusive = True
    xyClearanceInput.maximumValue = 0.05
    xyClearanceInput.isMaximumInclusive = True

    binDimensionsGroup = inputs.addGroupCommandInput(BIN_DIMENSIONS_GROUP, 'Main dimensions')
    binDimensionsGroup.isExpanded = uiState.getGroupExpandedState(BIN_DIMENSIONS_GROUP)
    binDimensionsGroup.tooltipDescription = 'Set in base units'
    binDimensionsGroup.children.addIntegerSpinnerCommandInput(BIN_WIDTH_INPUT_ID, 'Bin width (u)', 1, 100, 1, uiState.binWidth)
    binDimensionsGroup.children.addIntegerSpinnerCommandInput(BIN_LENGTH_INPUT_ID, 'Bin length (u)', 1, 100, 1, uiState.binLength)
    binHeightInput = binDimensionsGroup.children.addValueInput(BIN_HEIGHT_INPUT_ID, 'Bin height (u)', '', adsk.core.ValueInput.createByReal(uiState.binHeight))
    binHeightInput.minimumValue = 1
    binHeightInput.isMinimumInclusive = True

    actualDimensionsTable = render_actual_bin_dimensions_table(binDimensionsGroup.children)
    update_actual_bin_dimensions(
        actualDimensionsTable,
        adsk.core.ValueInput.createByReal(const.DIMENSION_DEFAULT_WIDTH_UNIT * 2 - const.BIN_XY_TOLERANCE * 2),
        adsk.core.ValueInput.createByReal(const.DIMENSION_DEFAULT_WIDTH_UNIT * 3 - const.BIN_XY_TOLERANCE * 2),
        adsk.core.ValueInput.createByReal(const.DIMENSION_DEFAULT_HEIGHT_UNIT * 5 + const.BIN_LIP_EXTRA_HEIGHT - const.BIN_LIP_TOP_RECESS_HEIGHT))
    staticInputCache.actualBinDimensionsTable = actualDimensionsTable

    binFeaturesGroup = inputs.addGroupCommandInput(BIN_FEATURES_GROUP, 'Bin features')
    binFeaturesGroup.isExpanded = uiState.getGroupExpandedState(BIN_FEATURES_GROUP)
    binFeaturesGroup.children.addBoolValueInput(BIN_GENERATE_BODY_INPUT_ID, 'Generate body', True, '', uiState.hasBody)
    binTypeDropdown = binFeaturesGroup.children.addDropDownCommandInput(BIN_TYPE_DROPDOWN_ID, 'Bin type', adsk.core.DropDownStyles.LabeledIconDropDownStyle)
    binTypeDropdown.listItems.add(BIN_TYPE_HOLLOW, uiState.binBodyType == BIN_TYPE_HOLLOW)
    binTypeDropdown.listItems.add(BIN_TYPE_SHELLED, uiState.binBodyType == BIN_TYPE_SHELLED)
    binTypeDropdown.listItems.add(BIN_TYPE_SOLID, uiState.binBodyType == BIN_TYPE_SOLID)

    binWallThicknessInput = binFeaturesGroup.children.addValueInput(BIN_WALL_THICKNESS_INPUT_ID, 'Bin wall thickness', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.binWallThickness))
    binWallThicknessInput.minimumValue = 0.04
    binWallThicknessInput.isMinimumInclusive = True
    binWallThicknessInput.maximumValue = 0.2
    binWallThicknessInput.isMaximumInclusive = True
    binFeaturesGroup.children.addBoolValueInput(BIN_WITH_LIP_INPUT_ID, 'Generate lip for stackability', True, '', uiState.hasLip)
    hasLipNotches = binFeaturesGroup.children.addBoolValueInput(BIN_WITH_LIP_NOTCHES_INPUT_ID, 'Generate lip notches', True, '', uiState.hasLipNotches)
    hasLipNotches.isEnabled = uiState.hasLip

    baseFeaturesGroup = inputs.addGroupCommandInput(BIN_BASE_FEATURES_GROUP_ID, 'Base interface features')
    baseFeaturesGroup.isExpanded = uiState.getGroupExpandedState(BIN_BASE_FEATURES_GROUP_ID)
    baseFeaturesGroup.children.addBoolValueInput(BIN_GENERATE_BASE_INPUT_ID, 'Generate base', True, '', uiState.hasBase)
    baseFeaturesGroup.children.addBoolValueInput(BIN_SCREW_HOLES_INPUT_ID, 'Add screw holes', True, '', uiState.hasBaseScrewHole)
    screwSizeInput = baseFeaturesGroup.children.addValueInput(BIN_SCREW_DIAMETER_INPUT, 'Screw hole diameter', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.baseScrewHoleSize))
    screwSizeInput.minimumValue = 0.1
    screwSizeInput.isMinimumInclusive = True
    screwSizeInput.maximumValue = 1
    screwSizeInput.isMaximumInclusive = True
    baseFeaturesGroup.children.addBoolValueInput(BIN_MAGNET_CUTOUTS_INPUT_ID, 'Add magnet cutouts', True, '', uiState.hasBaseMagnetSockets)
    magnetSizeInput = baseFeaturesGroup.children.addValueInput(BIN_MAGNET_DIAMETER_INPUT, 'Magnet cutout diameter', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.baseMagnetSocketSize))
    magnetSizeInput.minimumValue = 0.1
    magnetSizeInput.isMinimumInclusive = True
    magnetSizeInput.maximumValue = 1
    magnetSizeInput.isMaximumInclusive = True
    magnetHeightInput = baseFeaturesGroup.children.addValueInput(BIN_MAGNET_HEIGHT_INPUT, 'Magnet cutout depth', defaultLengthUnits, adsk.core.ValueInput.createByReal(uiState.baseMagnetSocketDepth))
    magnetHeightInput.minimumValue = 0.1
    magnetHeightInput.isMinimumInclusive = True

    userChangesGroup = inputs.addGroupCommandInput(USER_CHANGES_GROUP_ID, 'Changes')
    userChangesGroup.isExpanded = uiState.getGroupExpandedState(USER_CHANGES_GROUP_ID)
    preserveInputsRadioGroup = userChangesGroup.children.addRadioButtonGroupCommandInput(PRESERVE_CHAGES_RADIO_GROUP, 'Preserve inputs')
    preserveInputsRadioGroup.listItems.add(PRESERVE_CHAGES_RADIO_GROUP_RESET, not uiState.preserveChanges)
    preserveInputsRadioGroup.listItems.add(PRESERVE_CHAGES_RADIO_GROUP_PRESERVE, uiState.preserveChanges)
    preserveInputsRadioGroup.isFullWidth = True
    # preserveChangesDescription = userChangesGroup.children.addTextBoxCommandInput(PRESERVE_CHAGES_RADIO_GROUP + "_description", "", "Inputs will be persisted until Fusion is closed or reset option is selected", 2, True)
    # preserveChangesDescription.isFullWidth = True
    # showPreviewManual = userChangesGroup.children.addBoolValueInput(SHOW_PREVIEW_MANUAL_INPUT, 'Update preview once', False, '', False)


    previewGroup = inputs.addGroupCommandInput(PREVIEW_GROUP_ID, 'Preview')
    previewGroup.isExpanded = uiState.getGroupExpandedState(PREVIEW_GROUP_ID)
    previewGroup.children.addBoolValueInput(SHOW_PREVIEW_INPUT, 'Show auto update preview (slow)', True, '', False)
    showPreviewManual = previewGroup.children.addBoolValueInput(SHOW_PREVIEW_MANUAL_INPUT, 'Update preview once', False, '', False)
    showPreviewManual.isFullWidth = True

    # TODO Connect to the events that are needed by this command.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    generateBin(args)

# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs
    if is_all_input_valid(inputs):
        showPreview: adsk.core.BoolValueCommandInput = inputs.itemById(SHOW_PREVIEW_INPUT)
        showPreviewManual: adsk.core.BoolValueCommandInput = inputs.itemById(SHOW_PREVIEW_MANUAL_INPUT)
        if showPreview.value or showPreviewManual.value:
            args.isValidResult = generateBin(args)
            showPreviewManual.value = False
    else:
        args.executeFailed = True
        args.executeFailedMessage = "Some inputs are invalid, unable to generate preview"

def record_input_change(changed_input: adsk.core.CommandInput):
    if changed_input.id == BIN_BASE_WIDTH_UNIT_INPUT_ID:
        uiState.baseWidth = changed_input.value
    elif changed_input.id == BIN_BASE_LENGTH_UNIT_INPUT_ID:
        uiState.baseLength = changed_input.value
    elif changed_input.id == BIN_HEIGHT_UNIT_INPUT_ID:
        uiState.heightUnit = changed_input.value
    elif changed_input.id == BIN_HEIGHT_UNIT_INPUT_ID:
        uiState.xyTolerance = changed_input.value
    elif changed_input.id == BIN_WIDTH_INPUT_ID:
        uiState.binWidth = changed_input.value
    elif changed_input.id == BIN_LENGTH_INPUT_ID:
        uiState.binLength = changed_input.value
    elif changed_input.id == BIN_HEIGHT_INPUT_ID:
        uiState.binHeight = changed_input.value
    elif changed_input.id == BIN_GENERATE_BODY_INPUT_ID:
        uiState.hasBody = changed_input.value
    elif changed_input.id == BIN_TYPE_DROPDOWN_ID:
        uiState.binBodyType = changed_input.selectedItem.name
    elif changed_input.id == BIN_WALL_THICKNESS_INPUT_ID:
        uiState.binWallThickness = changed_input.value
    elif changed_input.id == BIN_WITH_LIP_INPUT_ID:
        uiState.hasLip = changed_input.value
    elif changed_input.id == BIN_WITH_LIP_NOTCHES_INPUT_ID:
        uiState.hasLipNotches = changed_input.value
    elif changed_input.id == BIN_GENERATE_BASE_INPUT_ID:
        uiState.hasBase = changed_input.value
    elif changed_input.id == BIN_SCREW_HOLES_INPUT_ID:
        uiState.hasBaseScrewHole = changed_input.value
    elif changed_input.id == BIN_SCREW_DIAMETER_INPUT:
        uiState.baseScrewHoleSize = changed_input.value
    elif changed_input.id == BIN_MAGNET_CUTOUTS_INPUT_ID:
        uiState.hasBaseMagnetSockets = changed_input.value
    elif changed_input.id == BIN_MAGNET_DIAMETER_INPUT:
        uiState.baseMagnetSocketSize = changed_input.value
    elif changed_input.id == BIN_MAGNET_HEIGHT_INPUT:
        uiState.baseMagnetSocketDepth = changed_input.value
    elif changed_input.id == PRESERVE_CHAGES_RADIO_GROUP:
        uiState.preserveChanges = changed_input.selectedItem.name == PRESERVE_CHAGES_RADIO_GROUP_PRESERVE
    elif changed_input.classType() == adsk.core.GroupCommandInput.classType():
        group_input: adsk.core.GroupCommandInput = changed_input
        uiState.groups[group_input.id] = group_input.isExpanded

def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    record_input_change(changed_input)
    inputs = args.inputs

    showPreview: adsk.core.BoolValueCommandInput = inputs.itemById(SHOW_PREVIEW_INPUT)
    showPreviewManual: adsk.core.BoolValueCommandInput = inputs.itemById(SHOW_PREVIEW_MANUAL_INPUT)
    wallThicknessInput: adsk.core.ValueCommandInput = inputs.itemById(BIN_WALL_THICKNESS_INPUT_ID)
    hasScrewHolesInput: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCREW_HOLES_INPUT_ID)
    hasBase: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BASE_INPUT_ID)
    hasBody: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BODY_INPUT_ID)
    binTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_TYPE_DROPDOWN_ID)
    hasMagnetCutoutsInput: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_CUTOUTS_INPUT_ID)
    magnetCutoutDiameterInput: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_DIAMETER_INPUT)
    magnetCutoutDepthInput: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_HEIGHT_INPUT)
    screwHoleDiameterInput: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCREW_DIAMETER_INPUT)
    withLipInput: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_INPUT_ID)
    withLipNotchesInput: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_NOTCHES_INPUT_ID)

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')

    try:
        if changed_input.id in [
            BIN_BASE_WIDTH_UNIT_INPUT_ID,
            BIN_BASE_LENGTH_UNIT_INPUT_ID,
            BIN_HEIGHT_UNIT_INPUT_ID,
            BIN_XY_TOLERANCE_INPUT_ID,
            BIN_WIDTH_INPUT_ID,
            BIN_LENGTH_INPUT_ID,
            BIN_HEIGHT_INPUT_ID,
            BIN_WITH_LIP_INPUT_ID
        ]:
            actualWidth = uiState.baseWidth * uiState.binWidth - uiState.xyTolerance * 2
            actualLength = uiState.baseLength * uiState.binLength - uiState.xyTolerance * 2
            actualHeight = uiState.heightUnit * uiState.binHeight + ((const.BIN_LIP_EXTRA_HEIGHT - const.BIN_LIP_TOP_RECESS_HEIGHT) if uiState.hasLip else 0)
            update_actual_bin_dimensions(
                staticInputCache.actualBinDimensionsTable,
                adsk.core.ValueInput.createByReal(actualWidth),
                adsk.core.ValueInput.createByReal(actualLength),
                adsk.core.ValueInput.createByReal(actualHeight),
                )

        if changed_input.id == BIN_TYPE_DROPDOWN_ID:
            selectedItem = binTypeDropdownInput.selectedItem.name
            if selectedItem == BIN_TYPE_HOLLOW:
                wallThicknessInput.isEnabled = True
            elif selectedItem == BIN_TYPE_SHELLED:
                wallThicknessInput.isEnabled = True
            elif selectedItem == BIN_TYPE_SOLID:
                wallThicknessInput.isEnabled = False
        elif changed_input.id == BIN_GENERATE_BASE_INPUT_ID:
            hasScrewHolesInput.isEnabled = hasBase.value
            hasMagnetCutoutsInput.isEnabled = hasBase.value
            magnetCutoutDiameterInput.isEnabled = hasBase.value
            magnetCutoutDepthInput.isEnabled = hasBase.value
            screwHoleDiameterInput.isEnabled = hasBase.value
        elif changed_input.id == BIN_GENERATE_BODY_INPUT_ID:
            wallThicknessInput.isEnabled = hasBody.value
            withLipInput.isEnabled = hasBody.value
            withLipNotchesInput.isEnabled = hasBody.value
        elif changed_input.id == BIN_WITH_LIP_INPUT_ID:
            withLipNotchesInput.isEnabled = withLipInput.value
        elif changed_input.id == SHOW_PREVIEW_INPUT:
            showPreviewManual.isVisible = not showPreview.value

    except:
        showErrorInMessageBox()



# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs = args.inputs

    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    args.areInputsValid = is_all_input_valid(inputs)


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event "{args.terminationReason}"')
    global local_handlers
    local_handlers = []
    global uiState
    if not uiState.preserveChanges and args.terminationReason == adsk.core.CommandTerminationReason.CompletedTerminationReason:
        uiState = defaultUiState()

def generateBin(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs
    base_width_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_WIDTH_UNIT_INPUT_ID)
    base_length_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_LENGTH_UNIT_INPUT_ID)
    height_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_UNIT_INPUT_ID)
    xy_tolerance: adsk.core.ValueCommandInput = inputs.itemById(BIN_XY_TOLERANCE_INPUT_ID)
    bin_width: adsk.core.ValueCommandInput = inputs.itemById(BIN_WIDTH_INPUT_ID)
    bin_length: adsk.core.ValueCommandInput = inputs.itemById(BIN_LENGTH_INPUT_ID)
    bin_height: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_INPUT_ID)
    bin_wall_thickness: adsk.core.ValueCommandInput = inputs.itemById(BIN_WALL_THICKNESS_INPUT_ID)
    bin_screw_holes: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_SCREW_HOLES_INPUT_ID)
    bin_generate_base: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BASE_INPUT_ID)
    bin_generate_body: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BODY_INPUT_ID)
    bin_magnet_cutouts: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_MAGNET_CUTOUTS_INPUT_ID)
    bin_screw_hole_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCREW_DIAMETER_INPUT)
    bin_magnet_cutout_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_DIAMETER_INPUT)
    bin_magnet_cutout_depth: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_HEIGHT_INPUT)
    with_lip: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_INPUT_ID)
    with_lip_notches: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_NOTCHES_INPUT_ID)
    binTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_TYPE_DROPDOWN_ID)

    isHollow = binTypeDropdownInput.selectedItem.name == BIN_TYPE_HOLLOW
    isSolid = binTypeDropdownInput.selectedItem.name == BIN_TYPE_SOLID
    isShelled = binTypeDropdownInput.selectedItem.name == BIN_TYPE_SHELLED

    # Do something interesting
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        root = adsk.fusion.Component.cast(des.rootComponent)
        tolerance = xy_tolerance.value
        binName = 'Gridfinity bin {}x{}x{}'.format(int(bin_length.value), int(bin_width.value), int(bin_height.value))

        # create new component
        newCmpOcc = adsk.fusion.Occurrences.cast(root.occurrences).addNewComponent(adsk.core.Matrix3D.create())
        newCmpOcc.component.name = binName
        newCmpOcc.activate()
        gridfinityBinComponent: adsk.fusion.Component = newCmpOcc.component
        features: adsk.fusion.Features = gridfinityBinComponent.features

        # create base interface
        baseGeneratorInput = BaseGeneratorInput()
        baseGeneratorInput.originPoint = gridfinityBinComponent.originConstructionPoint.geometry
        baseGeneratorInput.baseWidth = base_width_unit.value
        baseGeneratorInput.baseLength = base_length_unit.value
        baseGeneratorInput.xyTolerance = tolerance
        baseGeneratorInput.hasScrewHoles = bin_screw_holes.value and not isShelled
        baseGeneratorInput.hasMagnetCutouts = bin_magnet_cutouts.value and not isShelled
        baseGeneratorInput.screwHolesDiameter = bin_screw_hole_diameter.value
        baseGeneratorInput.magnetCutoutsDiameter = bin_magnet_cutout_diameter.value
        baseGeneratorInput.magnetCutoutsDepth = bin_magnet_cutout_depth.value

        baseBody: adsk.fusion.BRepBody

        if bin_generate_base.value:
            baseBody = createGridfinityBase(baseGeneratorInput, gridfinityBinComponent)
            # replicate base in rectangular pattern
            rectangularPatternFeatures: adsk.fusion.RectangularPatternFeatures = features.rectangularPatternFeatures
            patternInputBodies = adsk.core.ObjectCollection.create()
            patternInputBodies.add(baseBody)
            patternInput = rectangularPatternFeatures.createInput(patternInputBodies,
                gridfinityBinComponent.xConstructionAxis,
                adsk.core.ValueInput.createByReal(bin_width.value),
                adsk.core.ValueInput.createByReal(base_width_unit.value),
                adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
            patternInput.directionTwoEntity = gridfinityBinComponent.yConstructionAxis
            patternInput.quantityTwo = adsk.core.ValueInput.createByReal(bin_length.value)
            patternInput.distanceTwo = adsk.core.ValueInput.createByReal(base_length_unit.value)
            rectangularPattern = rectangularPatternFeatures.add(patternInput)


        # create bin body
        binBodyInput = BinBodyGeneratorInput()
        binBodyInput.hasLip = with_lip.value
        binBodyInput.hasLipNotches = with_lip_notches.value
        binBodyInput.binWidth = bin_width.value
        binBodyInput.binLength = bin_length.value
        binBodyInput.binHeight = bin_height.value
        binBodyInput.baseWidth = base_width_unit.value
        binBodyInput.baseLength = base_length_unit.value
        binBodyInput.heightUnit = height_unit.value
        binBodyInput.xyTolerance = tolerance
        binBodyInput.isSolid = isSolid or isShelled
        binBodyInput.wallThickness = bin_wall_thickness.value
        binBodyInput.hasScoop = False
        binBodyInput.hasTab = False
        binBodyInput.compartmentsByX = 1
        binBodyInput.compartmentsByY = 1
        binBodyInput.isLid = True

        binBodyInput.compartments = uniformCompartments(binBodyInput.compartmentsByX, binBodyInput.compartmentsByY)

        binBody: adsk.fusion.BRepBody

        if bin_generate_body.value:
            binBody = createGridfinityBinBody(
                binBodyInput,
                gridfinityBinComponent,
                )

        # merge everything
        if bin_generate_body.value and bin_generate_base.value:
            toolBodies = adsk.core.ObjectCollection.create()
            toolBodies.add(baseBody)
            for body in rectangularPattern.bodies:
                toolBodies.add(body)
            combineFeatures = gridfinityBinComponent.features.combineFeatures
            combineFeatureInput = combineFeatures.createInput(binBody, toolBodies)
            combineFeatures.add(combineFeatureInput)
            gridfinityBinComponent.bRepBodies.item(0).name = binName

        if isShelled and bin_generate_body.value:
            # face.boundingBox.maxPoint.z ~ face.boundingBox.minPoint.z => face horizontal
            # largest horizontal face
            horizontalFaces = [face for face in binBody.faces if geometryUtils.isHorizontal(face)]
            topFace = faceUtils.maxByArea(horizontalFaces)
            topFaceMinPoint = topFace.boundingBox.minPoint
            if binBodyInput.hasLip:
                splitBodyFeatures = features.splitBodyFeatures
                splitBodyInput = splitBodyFeatures.createInput(
                    binBody,
                    topFace,
                    True
                )
                splitBodies = splitBodyFeatures.add(splitBodyInput)
                bottomBody = min(splitBodies.bodies, key=lambda x: x.boundingBox.minPoint.z)
                topBody = max(splitBodies.bodies, key=lambda x: x.boundingBox.minPoint.z)
                horizontalFaces = [face for face in bottomBody.faces if geometryUtils.isHorizontal(face)]
                topFace = faceUtils.maxByArea(horizontalFaces)
                shellUtils.simpleShell([topFace], binBodyInput.wallThickness, gridfinityBinComponent)
                toolBodies = adsk.core.ObjectCollection.create()
                toolBodies.add(topBody)
                combineAfterShellFeatureInput = combineFeatures.createInput(bottomBody, toolBodies)
                combineFeatures.add(combineAfterShellFeatureInput)
                binBody = gridfinityBinComponent.bRepBodies.item(0)
            else:
                shellUtils.simpleShell([topFace], binBodyInput.wallThickness, gridfinityBinComponent)

            chamferEdge = [edge for edge in binBody.edges if geometryUtils.isHorizontal(edge)
                and math.isclose(edge.boundingBox.minPoint.z, topFaceMinPoint.z, abs_tol=const.DEFAULT_FILTER_TOLERANCE)
                and math.isclose(edge.boundingBox.minPoint.x, topFaceMinPoint.x, abs_tol=const.DEFAULT_FILTER_TOLERANCE)][0]
            if binBodyInput.hasLip and const.BIN_LIP_WALL_THICKNESS - binBodyInput.wallThickness > 0:
                chamferFeatures: adsk.fusion.ChamferFeatures = features.chamferFeatures
                chamferInput = chamferFeatures.createInput2()
                chamfer_edges = adsk.core.ObjectCollection.create()
                chamfer_edges.add(chamferEdge)
                chamferInput.chamferEdgeSets.addEqualDistanceChamferEdgeSet(chamfer_edges,
                    adsk.core.ValueInput.createByReal(const.BIN_LIP_WALL_THICKNESS - binBodyInput.wallThickness),
                    True)
                chamferFeatures.add(chamferInput)
    except:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        return False
    return True