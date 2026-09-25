#-----------------------------------------------------------------------------
set(MODULE_NAME GenericSpecimenManager)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  )

# Every file under Resources/ has to be listed: only what is listed is installed with the extension.
# (Regenerate the list after adding/moving files:  cd GenericSpecimenManager/GenericSpecimenManager &&
#  find Resources -type f ! -name '*.pyc' ! -path '*/__pycache__/*' | sort)
set(MODULE_PYTHON_RESOURCES
  Resources/Html/config_editor_help_cheatsheet.html
  Resources/Html/example_presets_template.html
  Resources/Html/module_help_cheatsheet.html
  Resources/Icons/${MODULE_NAME}.png
  Resources/Icons/${MODULE_NAME}.svg
  Resources/Presets/example_presets.json
  Resources/UI/${MODULE_NAME}.ui
  Resources/__init__.py
  Resources/core/__init__.py
  Resources/core/config_model.py
  Resources/core/logging_setup.py
  Resources/core/pattern_check.py
  Resources/core/safe_io.py
  Resources/core/status.py
  Resources/definitions.py
  Resources/gui/__init__.py
  Resources/gui/annotation.py
  Resources/gui/config_editor/__init__.py
  Resources/gui/config_editor/batch_export_tab.py
  Resources/gui/config_editor/defaults_tab.py
  Resources/gui/config_editor/dialog.py
  Resources/gui/config_editor/general_tab.py
  Resources/gui/config_editor/helpers.py
  Resources/gui/config_editor/images_tab.py
  Resources/gui/config_editor/manual_tab.py
  Resources/gui/config_editor/markups_tab.py
  Resources/gui/config_editor/popups.py
  Resources/gui/config_editor/segment_editor_tab.py
  Resources/gui/config_editor/segmentation_tab.py
  Resources/gui/config_editor/volume_rendering_tab.py
  Resources/gui/config_editor/workspace_tab.py
  Resources/gui/help_dialog.py
  Resources/gui/main_widget.py
  Resources/gui/specimen_actions.py
  Resources/gui/specimen_table.py
  Resources/gui/study_setup.py
  Resources/paths.py
  Resources/study/__init__.py
  Resources/study/batch_processor.py
  Resources/study/logic.py
  Resources/study/specimen.py
  Resources/utils/__init__.py
  Resources/utils/config_location.py
  Resources/utils/segment_editor.py
  Resources/utils/slicer_ui.py
  Resources/utils/volume_rendering.py
  Resources/utils/workspace.py
  )



#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)

  # Register the unittest subclass in the main script as a ctest.
  # Note that the test will also be available at runtime.
  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)

  # Additional build-time testing
  add_subdirectory(Testing)
endif()
