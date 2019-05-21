%module mypaintlib

%{
#include "mypaintlib.hpp"
%}

%begin %{
#define SWIG_PYTHON_2_UNICODE
%}

%include "common.hpp"

%include "std_vector.i"
namespace std {
   %template(IntVector) vector<int>;
   %template(DoubleVector) vector<double>;
}

typedef struct { int x, y, w, h; } Rect;

%include "surface.hpp"
%include "brush.hpp"
%include "mapping.hpp"

%include "python_brush.hpp"
%include "tiledsurface.hpp"

%include "pixops.hpp"
%include "colorring.hpp"
%include "colorchanger_wash.hpp"
%include "colorchanger_crossed_bowl.hpp"
%include "fastpng.hpp"

%include "fill/fill_constants.hpp"
%include "fill/floodfill.hpp"
%include "fill/gap_detection.hpp"
%include "fill/morphology_swig.hpp"
%include "fill/blur_swig.hpp"
%include "brushsettings.hpp"

%include "gdkpixbuf2numpy.hpp"

%init %{
import_array();
%}

