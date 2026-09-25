cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(GenericSpecimenManager)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/dfajtai/GenericSpecimenManager")
set(EXTENSION_CATEGORY "Segmentation")
set(EXTENSION_CONTRIBUTORS "Daniel Fajtai (-)")
set(EXTENSION_DESCRIPTION "A JSON-configured module for repetitive, specimen-by-specimen segmentation and annotation work: consistent file and segment naming, per-specimen status tracking, and batch export of segments, statistics and markups into data that is safe to analyse automatically.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/dfajtai/GenericSpecimenManager/main/GenericSpecimenManager/GenericSpecimenManager/Resources/Icons/GenericSpecimenManager.png")
# TODO: add real screenshots (e.g. docs/images/*.png in this repo) and list their raw.githubusercontent.com URLs here
# set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/dfajtai/GenericSpecimenManager/main/docs/images/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(GenericSpecimenManager)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
