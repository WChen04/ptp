import json
import pandas as pd
import numpy as np
import folium
from folium.features import GeoJsonTooltip
from folium import plugins
import matplotlib.pyplot as plt
import colorsys
from branca.colormap import linear

def analyze_dc_traffic_data(geojson_file):
    """
    Analyze DC traffic data from a GeoJSON file and create a Folium map visualization.
    
    Parameters:
    -----------
    geojson_file : str
        Path to the GeoJSON file containing DC traffic data
    """
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    # Load the GeoJSON data
    print(f"Loading data from {geojson_file}...")
    try:
        with open(geojson_file, 'r') as f:
            data = json.load(f)
        print("Data loaded successfully")
    except json.JSONDecodeError:
        print("Error: The file is not valid JSON. Attempting to fix truncated JSON...")
        try:
            with open(geojson_file, 'r') as f:
                content = f.read()
            # Try to fix by adding closing brackets if truncated
            if not content.strip().endswith('}'):
                content = content + ']}}'
            data = json.loads(content)
            print("JSON fixed and loaded successfully")
        except:
            print("Unable to fix JSON file. Please check if the file is complete.")
            return None
    
    # Extract features and create a DataFrame for analysis
    features = data.get('features', [])
    if not features:
        print("No features found in the GeoJSON file")
        return None
    
    print(f"Found {len(features)} road segments")
    
    # Debug: Check coordinate structure of first few features
    print("\nChecking coordinate structure of first feature:")
    if features and len(features) > 0:
        first_geometry = features[0].get('geometry', {})
        first_coords = first_geometry.get('coordinates', [])
        print(f"Geometry type: {first_geometry.get('type')}")
        print(f"Coordinates structure: {type(first_coords)}")
        if first_coords and len(first_coords) > 0:
            print(f"First coordinate: {first_coords[0]}")
            if isinstance(first_coords[0], list) and len(first_coords[0]) > 0:
                print(f"  Type: {type(first_coords[0][0])}")
    
    # Create a list to store segment data
    segments = []
    
    for feature in features:
        props = feature.get('properties', {})
        geom = feature.get('geometry', {})
        
        # Extract the first and last coordinates for line direction
        coords = geom.get('coordinates', [])
        start_coord = coords[0] if coords else None
        end_coord = coords[-1] if coords else None
        
        # Calculate segment length (approximate)
        length_km = 0
        if coords and len(coords) > 1:
            from math import radians, sin, cos, sqrt, atan2
            def haversine(coord1, coord2):
                # Extract longitude and latitude, handling different coordinate formats
                # Some GeoJSON files have [lon, lat] format, others have [lon, lat, elevation]
                if isinstance(coord1, list) and len(coord1) >= 2:
                    lon1, lat1 = coord1[0], coord1[1]
                else:
                    lon1, lat1 = coord1, 0  # Fallback, should not happen
                    
                if isinstance(coord2, list) and len(coord2) >= 2:
                    lon2, lat2 = coord2[0], coord2[1]
                else:
                    lon2, lat2 = coord2, 0  # Fallback, should not happen
                
                # Calculate the distance between two points in km
                R = 6371  # Earth radius in km
                dlon = radians(lon2 - lon1)
                dlat = radians(lat2 - lat1)
                a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                return R * c
            
            try:
                for i in range(len(coords)-1):
                    length_km += haversine(coords[i], coords[i+1])
            except Exception as e:
                # If there's an error in calculation, just set length to 0
                print(f"Error calculating length for segment: {e}")
                length_km = 0
        
        segment = {
            'route_id': props.get('ROUTEID'),
            'aadt': props.get('AADT'),
            'aadt_year': props.get('AADT_YEAR'),
            'from_measure': props.get('FROMMEASURE'),
            'to_measure': props.get('TOMEASURE'),
            'length_km': length_km,
            'gis_id': props.get('GIS_ID'),
            'object_id': props.get('OBJECTID'),
            'start_coord': start_coord,
            'end_coord': end_coord,
            'geometry': geom
        }
        segments.append(segment)
    
    # Create DataFrame
    df = pd.DataFrame(segments)
    
    # Basic statistics
    print("\n=== Traffic Volume Statistics ===")
    print(f"Average AADT: {df['aadt'].mean():.1f}")
    print(f"Median AADT: {df['aadt'].median():.1f}")
    print(f"Min AADT: {df['aadt'].min()}")
    print(f"Max AADT: {df['aadt'].max()}")
    
    # Calculate traffic volume categories
    traffic_ranges = {
        '0-1000': len(df[df['aadt'] <= 1000]),
        '1001-5000': len(df[(df['aadt'] > 1000) & (df['aadt'] <= 5000)]),
        '5001-10000': len(df[(df['aadt'] > 5000) & (df['aadt'] <= 10000)]),
        '10001+': len(df[df['aadt'] > 10000])
    }
    print("\nTraffic Volume Distribution:")
    for range_name, count in traffic_ranges.items():
        print(f"{range_name}: {count} segments ({count/len(df)*100:.1f}%)")
    
    # Route statistics
    print("\n=== Route Statistics ===")
    route_stats = df.groupby('route_id').agg({
        'aadt': ['mean', 'min', 'max', 'count'],
        'length_km': 'sum'
    })
    route_stats.columns = ['avg_aadt', 'min_aadt', 'max_aadt', 'segment_count', 'total_length_km']
    print(route_stats.sort_values('avg_aadt', ascending=False))
    
    # Create folium map
    print("\nCreating Folium map visualization...")
    
    # Determine center of map (average of all coordinates)
    all_lats = []
    all_lons = []
    
    for feature in features:
        geometry = feature.get('geometry', {})
        coords = geometry.get('coordinates', [])
        
        # Handle different geometry types and coordinate formats
        if geometry.get('type') == 'LineString':
            for coord in coords:
                if isinstance(coord, list) and len(coord) >= 2:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])
    
    if not all_lats or not all_lons:
        # Default to DC center if no coordinates
        center = [38.9072, -77.0369]
    else:
        # Calculate average lat/lon for centering
        center = [np.mean(all_lats), np.mean(all_lons)]
    
    # Create base map
    m = folium.Map(location=center, zoom_start=13, tiles='cartodbpositron')
    
    # Create colormap for traffic volumes
    min_traffic = df['aadt'].min()
    max_traffic = df['aadt'].max()
    colormap = linear.YlOrRd_09.scale(min_traffic, max_traffic)
    colormap.caption = 'Average Annual Daily Traffic (AADT)'
    m.add_child(colormap)
    
    # Group features by route for layer organization
    routes = {}
    for feature in features:
        props = feature.get('properties', {})
        route_id = props.get('ROUTEID')
        
        if not route_id:
            continue
            
        if route_id not in routes:
            routes[route_id] = []
            
        routes[route_id].append(feature)
    
    # Create a feature group for each route
    for route_id, route_features in routes.items():
        fg = folium.FeatureGroup(name=f"Route {route_id}")
        
        for feature in route_features:
            props = feature.get('properties', {})
            
            # Choose color based on AADT
            aadt = props.get('AADT')
            if not aadt:
                continue
                
            # Determine line width based on AADT (thicker for higher traffic)
            if aadt <= 1000:
                weight = 2
            elif aadt <= 5000:
                weight = 4
            elif aadt <= 10000:
                weight = 6
            else:
                weight = 8
            
            # Create a GeoJSON feature for the segment
            geojson_segment = {
                'type': 'Feature',
                'geometry': feature.get('geometry'),
                'properties': {
                    'AADT': aadt,
                    'RouteID': route_id,
                    'Year': props.get('AADT_YEAR'),
                    'ObjectID': props.get('OBJECTID'),
                    'FromMeasure': props.get('FROMMEASURE'),
                    'ToMeasure': props.get('TOMEASURE')
                }
            }
            
            # Add segment to feature group
            try:
                gj = folium.GeoJson(
                    geojson_segment,
                    style_function=lambda x, aadt=aadt, weight=weight: {
                        'color': colormap(aadt),
                        'weight': weight,
                        'opacity': 0.8
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=['RouteID', 'AADT', 'Year', 'ObjectID'],
                        aliases=['Route ID:', 'Traffic Volume:', 'Year:', 'Segment ID:'],
                        localize=True,
                        sticky=False,
                        labels=True,
                        style="""
                            background-color: #F0EFEF;
                            border: 1px solid gray;
                            border-radius: 3px;
                            box-shadow: 3px 3px 3px rgba(0,0,0,0.2);
                            font-size: 12px;
                            padding: 5px;
                        """
                    )
                )
                gj.add_to(fg)
            except Exception as e:
                print(f"Error adding segment to map: {e}")
                continue
                
        fg.add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add fullscreen button
    plugins.Fullscreen().add_to(m)
    
    # Add location finder
    plugins.LocateControl().add_to(m)
    
    # Add measure tool
    plugins.MeasureControl(position='topright', primary_length_unit='kilometers').add_to(m)
    
    # Save map to HTML file
    output_file = 'dc_traffic_map.html'
    m.save(output_file)
    print(f"Map saved to {output_file}")
    
    return df, m
# Main execution
if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        geojson_file = sys.argv[1]
    else:
        # Default file name
        geojson_file = "2022_Traffic_Volume.geojson"  # Change this to your actual file path
    
    try:
        # Analyze data and create map
        df, map_obj = analyze_dc_traffic_data(geojson_file)
        
        # Create analysis plots if data was successfully processed
        print("Open dc_traffic_map.html in a web browser to view the interactive map")
    except Exception as e:
        print(f"\nAn error occurred during analysis: {e}")
        import traceback
        traceback.print_exc()
