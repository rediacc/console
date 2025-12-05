/**
 * Test the SecureMemoryStorage implementation
 * Run this test in the browser console to verify functionality
 */

/* eslint-disable no-console */
import { secureStorage } from './secureMemoryStorage';

export async function testSecureStorage() {
  console.log('🔐 Testing SecureMemoryStorage with AES-GCM encryption...');

  try {
    // Test 1: Basic encryption and decryption
    console.log('\n✅ Test 1: Basic encryption/decryption');
    const testData =
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';
    await secureStorage.setItem('test_token', testData);
    const retrieved = await secureStorage.getItem('test_token');
    console.log('Original:', testData.substring(0, 50) + '...');
    console.log('Retrieved:', retrieved?.substring(0, 50) + '...');
    console.log('Match:', testData === retrieved ? '✅ PASS' : '❌ FAIL');

    // Test 2: Multiple items
    console.log('\n✅ Test 2: Multiple items');
    await secureStorage.setItem('user_email', 'test@example.com');
    await secureStorage.setItem('user_company', 'Test Corp');
    const email = await secureStorage.getItem('user_email');
    const company = await secureStorage.getItem('user_company');
    console.log('Email:', email, email === 'test@example.com' ? '✅' : '❌');
    console.log('Company:', company, company === 'Test Corp' ? '✅' : '❌');

    // Test 3: Non-existent key
    console.log('\n✅ Test 3: Non-existent key');
    const notFound = await secureStorage.getItem('non_existent');
    console.log('Non-existent key returns null:', notFound === null ? '✅ PASS' : '❌ FAIL');

    // Test 4: Remove item
    console.log('\n✅ Test 4: Remove item');
    secureStorage.removeItem('test_token');
    const removed = await secureStorage.getItem('test_token');
    console.log('Removed item returns null:', removed === null ? '✅ PASS' : '❌ FAIL');

    // Test 5: Clear all
    console.log('\n✅ Test 5: Clear all items');
    secureStorage.clear();
    const clearedEmail = await secureStorage.getItem('user_email');
    const clearedCompany = await secureStorage.getItem('user_company');
    console.log(
      'All items cleared:',
      clearedEmail === null && clearedCompany === null ? '✅ PASS' : '❌ FAIL'
    );

    // Test 6: Special characters and Unicode
    console.log('\n✅ Test 6: Special characters and Unicode');
    const specialData = '🔐 Special chars: !@#$%^&*()_+-=[]{}|;\':"<>?,./';
    await secureStorage.setItem('special', specialData);
    const retrievedSpecial = await secureStorage.getItem('special');
    console.log(
      'Unicode and special chars:',
      specialData === retrievedSpecial ? '✅ PASS' : '❌ FAIL'
    );

    // Test 7: Large data
    console.log('\n✅ Test 7: Large data encryption');
    const largeData = 'x'.repeat(10000);
    const start = performance.now();
    await secureStorage.setItem('large', largeData);
    const retrievedLarge = await secureStorage.getItem('large');
    const duration = performance.now() - start;
    console.log(
      `Large data (10KB) encrypted in ${duration.toFixed(2)}ms:`,
      largeData === retrievedLarge ? '✅ PASS' : '❌ FAIL'
    );

    // Test 8: Security - Data tampering detection
    console.log('\n✅ Test 8: Tampering detection');
    await secureStorage.setItem('tamper_test', 'original data');

    // Try to manually tamper with the encrypted data
    const storage = (secureStorage as unknown as { storage: Map<string, unknown> }).storage;
    const encryptedData = storage.get('tamper_test') as { ciphertext: string } | undefined;
    if (encryptedData) {
      // Tamper with the ciphertext
      const tamperedData = {
        ...encryptedData,
        ciphertext:
          encryptedData.ciphertext.substring(0, encryptedData.ciphertext.length - 2) + 'XX',
      };
      storage.set('tamper_test', tamperedData);

      // Try to decrypt tampered data
      const tampered = await secureStorage.getItem('tamper_test');
      console.log(
        'Tampered data returns empty (auth failed):',
        tampered === '' ? '✅ PASS' : '❌ FAIL'
      );
    }

    // Cleanup
    secureStorage.clear();

    console.log('\n🎉 All tests completed!');
  } catch (error) {
    console.error('❌ Test failed with error:', error);
  }
}

// Export for browser console testing
declare global {
  interface Window {
    testSecureStorage?: typeof testSecureStorage;
  }
}

if (typeof window !== 'undefined') {
  window.testSecureStorage = testSecureStorage;
}
