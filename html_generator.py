"""
DC Traffic Map Generator

This script generates an interactive map of Washington DC traffic volumes.
It handles GeoJSON files with LineString geometries and AADT (Annual Average Daily Traffic) data.
"""

import json
import pandas as pd
import numpy as np
import folium
from folium.features import GeoJsonTooltip
import branca.colormap as cm

def generate_traffic_map(filename):
    """Generate a Folium map from a GeoJSON file with traffic data"""
    print(f"Loading GeoJSON file: {filename}")
    
    # Load the GeoJSON data
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            print("File loaded successfully")
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        print("Attempting to fix truncated file...")
        
        try:
            with open(filename, 'r') as f:
                content = f.read()
            
            # Try to fix truncated file
            fixed_content = content + "]}"
            data = json.loads(fixed_content)
            print("Fixed JSON successfully")
        except Exception as e:
            print(f"Could not fix JSON: {e}")
            return None
    except Exception as e:
        print(f"Error loading file: {e}")
        return None
    
    # Check if we have features
    features = data.get('features', [])
    if not features:
        print("No features found in the GeoJSON file")
        return None
    
    print(f"Found {len(features)} features")
    
    # Create a map centered around DC
    dc_center = [38.9072, -77.0369]  # Washington DC
    m = folium.Map(location=dc_center, zoom_start=12, tiles='CartoDB positron')
    
    # Sample some coordinates to get better centering
    sample_coords = []
    
    # Extract AADT values to create appropriate color scale
    aadt_values = []
    unique_routes = set()
    
    for feature in features:
        props = feature.get('properties', {})
        aadt = props.get('AADT')
        route_id = props.get('ROUTEID')
        
        if aadt:
            aadt_values.append(aadt)
        
        if route_id:
            unique_routes.add(route_id)
            
        # Sample coordinates from geometry
        geom = feature.get('geometry', {})
        if geom.get('type') == 'LineString':
            coords = geom.get('coordinates', [])
            if coords and len(coords) > 0:
                # Just take the first coordinate for sampling
                if len(coords) > 0 and isinstance(coords[0], list) and len(coords[0]) >= 2:
                    sample_coords.append([coords[0][1], coords[0][0]])  # [lat, lon]
    
    print(f"Found {len(unique_routes)} unique routes")
    print(f"AADT range: {min(aadt_values) if aadt_values else 0} - {max(aadt_values) if aadt_values else 0}")
    
    # Recenter map if we have enough coordinates
    if len(sample_coords) > 10:
        avg_lat = np.mean([coord[0] for coord in sample_coords])
        avg_lon = np.mean([coord[1] for coord in sample_coords])
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=12, tiles='CartoDB positron')
    
    # Create a colormap for AADT values
    if aadt_values:
        min_aadt = min(aadt_values)
        max_aadt = max(aadt_values)
        colormap = cm.LinearColormap(
            ['green', 'yellow', 'orange', 'red'],
            vmin=min_aadt,
            vmax=max_aadt
        )
        colormap.caption = 'Annual Average Daily Traffic'
        m.add_child(colormap)
    
    # Group features by route
    route_groups = {}
    for feature in features:
        props = feature.get('properties', {})
        route_id = props.get('ROUTEID')
        
        if route_id:
            if route_id not in route_groups:
                route_groups[route_id] = []
            route_groups[route_id].append(feature)
    
    # Create a feature group for each route
    for route_id, route_features in route_groups.items():
        fg = folium.FeatureGroup(name=f"Route {route_id}")
        
        for feature in route_features:
            props = feature.get('properties', {})
            aadt = props.get('AADT')
            
            if not aadt:
                continue
                
            # Determine line width based on traffic volume
            width = 2
            if aadt > 10000:
                width = 7
            elif aadt > 5000:
                width = 5
            elif aadt > 2000:
                width = 3
            
            # Create tooltip content
            tooltip_content = f"""
                <div style="font-family: Arial; font-size: 12px;">
                <b>Route:</b> {route_id}<br>
                <b>Traffic:</b> {aadt} vehicles/day<br>
                <b>Year:</b> {props.get('AADT_YEAR')}<br>
                </div>
            """
            
            # Add the feature to the map
            try:
                gj = folium.GeoJson(
                    feature,
                    style_function=lambda x, aadt=aadt, width=width: {
                        'color': colormap(aadt) if aadt_values else 'blue',
                        'weight': width,
                        'opacity': 0.8
                    }
                )
                folium.Tooltip(tooltip_content).add_to(gj)
                gj.add_to(fg)
            except Exception as e:
                print(f"Error adding segment to map: {e}")
        
        fg.add_to(m)
    
    # Add layer control to toggle routes
    folium.LayerControl().add_to(m)
    
    # Save the map to an HTML file
    output_file = 'dc_traffic_map.html'
    m.save(output_file)
    print(f"Map saved to {output_file}")
    
    return m

# Main execution
if __name__ == "__main__":
    import sys
    
    # Get filename from command-line or use default
    filename = sys.argv[1] if len(sys.argv) > 1 else "2022_Traffic_Volume.geojson"
    
    # Generate the map
    map_obj = generate_traffic_map(filename)
    
    if map_obj:
        print("Map generation successful!")
        print("Open dc_traffic_map.html in a web browser to view the map")
    else:
        print("Failed to generate map.")
