# __init__.py
def classFactory(iface):
   from .argentina_georef import ArgentinaGeoref
   return ArgentinaGeoref(iface)