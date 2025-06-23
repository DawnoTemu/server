#!/usr/bin/env python3
"""
API Key Generator for DawnoTemu Production System

This script generates cryptographically secure API keys for production use.
Multiple generation methods are provided for different security requirements.

Usage:
    python scripts/generate_api_key.py
    python scripts/generate_api_key.py --method uuid
    python scripts/generate_api_key.py --method hex --length 64
    python scripts/generate_api_key.py --prefix DT_ --method base64 --length 48
"""

import os
import sys
import argparse
import secrets
import string
import uuid
import base64
import hashlib
from datetime import datetime

class APIKeyGenerator:
    """Generate secure API keys using various methods"""
    
    @staticmethod
    def generate_hex_key(length: int = 64) -> str:
        """
        Generate a hexadecimal API key using cryptographically secure random bytes
        
        Args:
            length: Length of hex string (actual bytes will be length/2)
            
        Returns:
            str: Hexadecimal API key
        """
        # Generate random bytes (length/2 because each byte becomes 2 hex chars)
        random_bytes = secrets.token_bytes(length // 2)
        return random_bytes.hex()
    
    @staticmethod
    def generate_base64_key(length: int = 48) -> str:
        """
        Generate a base64url-encoded API key
        
        Args:
            length: Number of random bytes before encoding
            
        Returns:
            str: Base64url-encoded API key (URL-safe)
        """
        random_bytes = secrets.token_bytes(length)
        # Use URL-safe base64 (no padding)
        return base64.urlsafe_b64encode(random_bytes).decode('ascii').rstrip('=')
    
    @staticmethod
    def generate_uuid_key() -> str:
        """
        Generate a UUID4-based API key (cryptographically secure)
        
        Returns:
            str: UUID4 string without hyphens
        """
        return str(uuid.uuid4()).replace('-', '')
    
    @staticmethod
    def generate_alphanumeric_key(length: int = 64) -> str:
        """
        Generate an alphanumeric API key
        
        Args:
            length: Length of the generated key
            
        Returns:
            str: Alphanumeric API key
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_custom_key(prefix: str = "", suffix: str = "", method: str = "hex", length: int = 32) -> str:
        """
        Generate a custom API key with prefix/suffix
        
        Args:
            prefix: String to prepend to the key
            suffix: String to append to the key
            method: Generation method (hex, base64, uuid, alphanumeric)
            length: Length for methods that support it
            
        Returns:
            str: Custom formatted API key
        """
        if method == "hex":
            core_key = APIKeyGenerator.generate_hex_key(length)
        elif method == "base64":
            core_key = APIKeyGenerator.generate_base64_key(length)
        elif method == "uuid":
            core_key = APIKeyGenerator.generate_uuid_key()
        elif method == "alphanumeric":
            core_key = APIKeyGenerator.generate_alphanumeric_key(length)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return f"{prefix}{core_key}{suffix}"
    
    @staticmethod
    def generate_timestamped_key(method: str = "hex", length: int = 32) -> tuple:
        """
        Generate an API key with creation timestamp
        
        Args:
            method: Generation method
            length: Key length
            
        Returns:
            tuple: (api_key, timestamp, metadata)
        """
        timestamp = datetime.utcnow()
        key = APIKeyGenerator.generate_custom_key(method=method, length=length)
        
        metadata = {
            'key': key,
            'created_at': timestamp.isoformat(),
            'method': method,
            'length': length,
            'entropy_bits': APIKeyGenerator.calculate_entropy(key)
        }
        
        return key, timestamp, metadata
    
    @staticmethod
    def calculate_entropy(key: str) -> float:
        """
        Calculate the entropy bits of an API key
        
        Args:
            key: The API key string
            
        Returns:
            float: Entropy in bits
        """
        import math
        
        # Count unique characters
        unique_chars = len(set(key))
        key_length = len(key)
        
        # Calculate entropy: length * log2(character_set_size)
        if unique_chars > 0:
            # Estimate character set size based on unique characters
            if all(c in string.hexdigits.lower() for c in key.lower()):
                charset_size = 16  # Hex
            elif all(c in string.ascii_letters + string.digits for c in key):
                charset_size = 62  # Alphanumeric
            else:
                charset_size = unique_chars  # Conservative estimate
            
            entropy = key_length * math.log2(charset_size)
            return round(entropy, 2)
        
        return 0.0
    
    @staticmethod
    def validate_key_strength(key: str) -> dict:
        """
        Validate the strength of an API key
        
        Args:
            key: API key to validate
            
        Returns:
            dict: Validation results
        """
        results = {
            'length': len(key),
            'entropy_bits': APIKeyGenerator.calculate_entropy(key),
            'has_uppercase': any(c.isupper() for c in key),
            'has_lowercase': any(c.islower() for c in key),
            'has_digits': any(c.isdigit() for c in key),
            'has_special': any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in key),
            'strength': 'unknown'
        }
        
        # Determine strength based on entropy
        entropy = results['entropy_bits']
        if entropy >= 256:
            results['strength'] = 'excellent'
        elif entropy >= 128:
            results['strength'] = 'good'
        elif entropy >= 64:
            results['strength'] = 'fair'
        else:
            results['strength'] = 'weak'
        
        results['recommendations'] = []
        
        if results['length'] < 32:
            results['recommendations'].append('Consider using a longer key (32+ characters)')
        
        if entropy < 128:
            results['recommendations'].append('Consider using a method with higher entropy')
        
        return results


def print_key_info(key: str, method: str, metadata: dict = None):
    """Print formatted key information"""
    print("\n" + "="*80)
    print(f"🔑 GENERATED API KEY")
    print("="*80)
    print(f"Method: {method}")
    print(f"Key:    {key}")
    print(f"Length: {len(key)} characters")
    
    # Validate strength
    validation = APIKeyGenerator.validate_key_strength(key)
    print(f"Entropy: {validation['entropy_bits']} bits")
    print(f"Strength: {validation['strength'].upper()}")
    
    if metadata:
        print(f"Created: {metadata.get('created_at', 'N/A')}")
    
    print("\n📋 CONFIGURATION:")
    print("Add to your production .env file:")
    print(f"ADMIN_API_KEYS={key}")
    
    print("\n🚀 USAGE:")
    print("Use with upload script:")
    print(f"python scripts/upload_stories_to_production.py \\")
    print(f"  --server https://api.dawnotemu.app \\")
    print(f"  --api-key {key}")
    
    if validation['recommendations']:
        print("\n⚠️  RECOMMENDATIONS:")
        for rec in validation['recommendations']:
            print(f"  - {rec}")
    
    print("\n🔒 SECURITY NOTES:")
    print("  - Store this key securely (password manager, secure vault)")
    print("  - Never commit this key to version control")
    print("  - Rotate this key regularly (monthly/quarterly)")
    print("  - Monitor usage and revoke if compromised")
    print("="*80)


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description='Generate secure API keys for DawnoTemu')
    
    parser.add_argument('--method', 
                       choices=['hex', 'base64', 'uuid', 'alphanumeric'],
                       default='hex',
                       help='Key generation method (default: hex)')
    
    parser.add_argument('--length', 
                       type=int, 
                       default=64,
                       help='Key length for supported methods (default: 64)')
    
    parser.add_argument('--prefix', 
                       type=str, 
                       default='',
                       help='Prefix to add to the key (e.g., "DT_")')
    
    parser.add_argument('--suffix', 
                       type=str, 
                       default='',
                       help='Suffix to add to the key')
    
    parser.add_argument('--multiple', 
                       type=int, 
                       default=1,
                       help='Generate multiple keys (default: 1)')
    
    parser.add_argument('--validate', 
                       type=str,
                       help='Validate an existing API key')
    
    parser.add_argument('--show-methods', 
                       action='store_true',
                       help='Show information about available methods')
    
    args = parser.parse_args()
    
    if args.show_methods:
        print("\n🔧 AVAILABLE METHODS:")
        print("="*50)
        print("hex          - Hexadecimal (0-9, a-f)")
        print("base64       - Base64url encoding (URL-safe)")
        print("uuid         - UUID4 format (no hyphens)")
        print("alphanumeric - Letters and numbers (a-z, A-Z, 0-9)")
        print("\n📊 RECOMMENDED SETTINGS:")
        print("Production:  --method hex --length 64")
        print("High Security: --method base64 --length 48")
        print("Simple:      --method uuid")
        return
    
    if args.validate:
        print(f"\n🔍 VALIDATING KEY: {args.validate}")
        validation = APIKeyGenerator.validate_key_strength(args.validate)
        
        print(f"Length: {validation['length']} characters")
        print(f"Entropy: {validation['entropy_bits']} bits")
        print(f"Strength: {validation['strength'].upper()}")
        
        if validation['recommendations']:
            print("\nRecommendations:")
            for rec in validation['recommendations']:
                print(f"  - {rec}")
        return
    
    # Generate keys
    if args.multiple == 1:
        # Single key
        if args.method == 'uuid':
            key = APIKeyGenerator.generate_custom_key(
                prefix=args.prefix,
                suffix=args.suffix,
                method=args.method
            )
        else:
            key = APIKeyGenerator.generate_custom_key(
                prefix=args.prefix,
                suffix=args.suffix,
                method=args.method,
                length=args.length
            )
        
        key, timestamp, metadata = APIKeyGenerator.generate_timestamped_key(
            method=args.method,
            length=args.length if args.method != 'uuid' else 32
        )
        
        if args.prefix or args.suffix:
            key = f"{args.prefix}{key}{args.suffix}"
        
        print_key_info(key, args.method, metadata)
    
    else:
        # Multiple keys
        print(f"\n🔑 GENERATING {args.multiple} API KEYS")
        print("="*80)
        
        keys = []
        for i in range(args.multiple):
            if args.method == 'uuid':
                key = APIKeyGenerator.generate_custom_key(
                    prefix=args.prefix,
                    suffix=args.suffix,
                    method=args.method
                )
            else:
                key = APIKeyGenerator.generate_custom_key(
                    prefix=args.prefix,
                    suffix=args.suffix,
                    method=args.method,
                    length=args.length
                )
            
            keys.append(key)
            validation = APIKeyGenerator.validate_key_strength(key)
            print(f"{i+1:2d}. {key} ({validation['entropy_bits']} bits, {validation['strength']})")
        
        print(f"\n📋 CONFIGURATION:")
        print("Add to your production .env file:")
        keys_string = ','.join(keys)
        print(f"ADMIN_API_KEYS={keys_string}")


if __name__ == '__main__':
    main() 