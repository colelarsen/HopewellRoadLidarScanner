
import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
import pyproj
import asyncio
import httpx
import webbrowser

import whitebox
import whitebox_workflows as wbw
import geemap
import rioxarray as rxr
import rasterio
import earthpy as et
import earthpy.plot as ep
import matplotlib.pyplot as plt
import earthpy.spatial as es
import geopandas as gpd
from rasterio.plot import plotting_extent



def get_links_from_url(url):
    """
    Fetches a webpage and extracts all absolute links.
    """
    try:
        # Step 1: Fetch the web page content
        response = requests.get(url)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        html_content = response.text

        # Step 2: Parse the HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Step 3: Extract all anchor tags ('a')
        anchor_tags = soup.find_all('a')

        list_of_links = []
        for tag in anchor_tags:
            href = tag.get('href')
            if href and ".xml" in href:
                # Step 4: Resolve relative URLs to absolute URLs
                href = "metadata/" + href
                absolute_url = urljoin(url, href)
                list_of_links.append(absolute_url)
        
        return list_of_links

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return []

def is_point_in_boundary(point, west, east, north, south):
    """
    Check if a point is within the given boundary.
    """
    x, y = point
    return west <= x <= east and south <= y <= north


def check_is_point_in_xml(root, point):
    bounding = root.find('.//bounding')

    westbc = float(bounding.find('westbc').text)
    eastbc = float(bounding.find('eastbc').text)
    northbc = float(bounding.find('northbc').text)
    southbc = float(bounding.find('southbc').text)

    return is_point_in_boundary(point, westbc, eastbc, northbc, southbc)







async def check_point_from_url(link, gps_point, client):
    response_xml = await client.get(link)

    root = ET.fromstring(response_xml.content)

    point_in_boundary = check_is_point_in_xml(root, (gps_point['x'], gps_point['y']))

    data_root = {
        'link': link,
        'is_point_in_boundary': point_in_boundary,
        'laz': root.find('.//networkr').text
    }
    if point_in_boundary:
        print(f"Point is within boundary of XML: {link}")
        print(data_root['laz'])
        return data_root['laz']
    return False





#Maybe road?
# 39.714108, -82.788102




async def main_fetch():
    target_crs = 'epsg:3857' # Example: Web Mercator (common for many web maps)

    input_crs = 'epsg:4326' # WGS84 (standard GPS)

    transformer = pyproj.Transformer.from_crs(input_crs, target_crs, always_xy=True) # always_xy for (lon, lat) output






    x, y = -82.461096, 40.028172 # WGS84 (standard GPS) THIS IS THE INPUT POINT
    longitude, latitude = transformer.transform(x, y)

    print(f"Projected (X,Y): ({x}, {y})")
    print(f"GPS (Lon,Lat): ({longitude}, {latitude})")




    point = {"x":longitude,"y":latitude,"spatialReference":{"wkid":3857}}

    gps_point = {"x":x,"y":y,"spatialReference":{"wkid":4326}}

    print(point)

    url = 'https://index.nationalmap.gov/arcgis/rest/services/3DEPElevationIndex/MapServer/24/query?&f=json&returnGeometry=true&returnTrueCurves=false&spatialRel=esriSpatialRelIntersects&inSR=3857&outSR=3857&outfields=*&geometryType=esriGeometryPoint'
    url += f'&geometry={point}'

    response = requests.get(url)

    print(f"Fetching data from URL: {url}")

    data = json.loads(response.text)



    # Check the status code (200 means success)
    print(f"Status Code: {response.status_code}")

    print(data)

    # # Access the response content (text or JSON)
    # print(f"Response Text: {data['features'][0]['attributes']['lpc_link']}")
    # If the response is JSON, parse it into a Python dictionary
    # print(f"Response JSON: {response.json()}")

    # url_lpc = data['features'][0]['attributes']['lpc_link'] + '/metadata'
    response_links = []

    for featue in data['features']:
        lpc_link = featue['attributes']['lpc_link'] + '/metadata'
        links = get_links_from_url(lpc_link)
        response_links.extend(links)
    # print(response_links)

    print(f"Total XML links found: {response_links.__len__()}")

    #Run asynchronously to speed up?

    if response_links.__len__() > 2000:
        i = 0
        while i < response_links.__len__():
            print(f"Processing batch {i} : {i+2000}")
            batch_links = response_links[i:i+2000]
            async with httpx.AsyncClient() as client:
                tasks = [check_point_from_url(link, gps_point, client) for link in batch_links]
                results = await asyncio.gather(*tasks)

                for res in results:
                    if res:
                        print(f"Found LAZ link: {res}")
                        webbrowser.open(res)
            i += 2000
    else:
        async with httpx.AsyncClient() as client:
            tasks = [check_point_from_url(link, gps_point, client) for link in response_links]
            results = await asyncio.gather(*tasks)


def show_hillshade(wbt, input, output):
    wbt.hillshade(input, output, azimuth=120, altitude=35)

    geemap.add_crs(output,
                epsg=4326)
    
    # Read the raster using rioxarray
    idw_dem = rxr.open_rasterio(output)
    


    # View the raster
    ep.plot_bands(
        idw_dem,
        cbar=True,
        cmap="gray",
        title="Hillshade made from DTM",
        figsize=(12, 12),
        vmin=15000
    )

    plt.show();

def show_horizon_angle(wbt, input, output):
    wbt.horizon_angle(
    input, 
    output, 
    azimuth=120, 
    max_dist=45)

    geemap.add_crs(output,
                epsg=4326)
    
    # Read the raster using rioxarray
    idw_dem = rxr.open_rasterio(output)
    


    # View the raster
    ep.plot_bands(
        idw_dem,
        cbar=True,
        cmap="gray",
        title="Horizon Angle made from DTM",
        figsize=(12, 12),
        vmin=-10,
        vmax=10
    )

    plt.show();

def show_directional_relief(wbt, input, output):
    wbt.directional_relief(
    input, 
    output, 
    azimuth=120, 
    max_dist=None
)

    geemap.add_crs(output,
                epsg=4326)
    
    # Read the raster using rioxarray
    idw_dem = rxr.open_rasterio(output)
    


    # View the raster
    ep.plot_bands(
        idw_dem,
        cbar=True,
        cmap="gray",
        title="Directional Relief made from DTM",
        figsize=(12, 12),
        vmin=-10,
        vmax=10
    )

    plt.show();

def show_elev_relative_to_min_max(wbt, input, output):
    wbt.elev_relative_to_min_max(
    input, 
    output)

    geemap.add_crs(output,
                epsg=4326)
    
    # Read the raster using rioxarray
    idw_dem = rxr.open_rasterio(output)
    


    # View the raster
    ep.plot_bands(
        idw_dem,
        cbar=True,
        cmap="gray",
        title="Elev Relative to Min Max made from DTM",
        figsize=(12, 12)
    )

    plt.show();



def main():
    wbt = whitebox.WhiteboxTools()
    i="C:/Users/Cole/Downloads/lidar/USGS_LPC_OH_Statewide_Phase2_2020_B20_BS19800738.laz"
    off_ground_objects="C:/Users/Cole/Downloads/lidar/output/off_ground_objects.laz"

    dem="C:/Users/Cole/Downloads/lidar/output/modified.tif"
    dem_offground="C:/Users/Cole/Downloads/lidar/output/dem_offground.tif"
    final_output="C:/Users/Cole/Downloads/lidar/output/colorad_laz_info.tif"
    final_output_2="C:/Users/Cole/Downloads/lidar/output/colorad_laz_info_2.tif"


    #Get off ground points
    wbt.lidar_ground_point_filter(
    i, 
    off_ground_objects, 
    radius=2.0, 
    min_neighbours=0, 
    slope_threshold=45.0, 
    height_threshold=1.0, 
    classify=True, 
    slope_norm=True, 
    height_above_ground=True, 
    )

    # Now, create DEM from IDW interpolation
    print("Interpolating DEM...")
    wbt.lidar_idw_interpolation(
    i=i,
    output=dem,
    parameter="elevation",
    returns="all",
    resolution=1.0,
    weight=1.0,
    radius=2.5
    )

    # Now, create DEM from IDW interpolation
    print("Interpolating DEM...")
    wbt.lidar_idw_interpolation(
    i=off_ground_objects,
    output=dem_offground,
    parameter="elevation",
    returns="all",
    resolution=1.0,
    weight=1.0,
    radius=2.5
    )

    
    # Subtract off-ground DEM from original DEM to get ground-only DEM
    wbt.subtract(dem, dem_offground,
             output=final_output)
    
    
    #Hillshade is best so far imo
    show_hillshade(wbt, final_output, final_output_2)

    #Horizon angle is good
    # show_horizon_angle(wbt, final_output, final_output_2)

    #Directional relief is not great
    # show_directional_relief(wbt, final_output, final_output_2)

    #elev_relative_to_min_max was decent
    # show_elev_relative_to_min_max(wbt, final_output, final_output_2)



main()


#Uncomment below to run async fetch for grabbing LIDAR data
# if __name__ == '__main__':
#     asyncio.run(main_fetch())