#!/usr/bin/env python3
# validate_render.py
"""Validate render.yaml configuration."""

import yaml
from pathlib import Path

def validate_render_yaml():
    """Validate the render.yaml file."""
    render_file = Path('render.yaml')
    
    if not render_file.exists():
        print("❌ render.yaml not found")
        return False
    
    try:
        with open(render_file, 'r') as f:
            config = yaml.safe_load(f)
        
        print("✅ render.yaml is valid YAML")
        
        # Check required sections
        if 'services' not in config:
            print("❌ Missing 'services' section")
            return False
        
        if 'databases' not in config:
            print("❌ Missing 'databases' section")
            return False
        
        print("✅ Required sections present")
        
        # Check services
        services = config['services']
        service_types = [s.get('type', 'unknown') for s in services]
        
        print(f"📊 Services found:")
        for i, service in enumerate(services):
            name = service.get('name', f'service-{i}')
            service_type = service.get('type', 'unknown')
            print(f"   - {name}: {service_type}")
        
        # Check for required fields in each service
        valid_services = 0
        for service in services:
            service_name = service.get('name', 'unnamed')
            required_fields = ['type', 'name']
            
            missing_fields = [f for f in required_fields if f not in service]
            if missing_fields:
                print(f"❌ Service '{service_name}' missing fields: {missing_fields}")
            else:
                valid_services += 1
        
        print(f"✅ {valid_services}/{len(services)} services are valid")
        
        # Check databases
        databases = config['databases']
        print(f"📊 Databases found: {len(databases)}")
        for db in databases:
            name = db.get('name', 'unnamed')
            print(f"   - {name}")
        
        print("✅ render.yaml validation completed")
        return True
        
    except yaml.YAMLError as e:
        print(f"❌ YAML syntax error: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Validating render.yaml...")
    success = validate_render_yaml()
    exit(0 if success else 1)