import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useAccountsStore } from '@/stores';
import { useGenlayer } from '@/hooks';
import { generatePrivateKey, createAccount } from 'genlayer-js';

const testKey1 =
  '0xb69426b0f5838a514b263868978faaa53057ac83c5ccad6b7fddbc051b052c6a'; // ! NEVER USE THIS PRIVATE KEY
const testAddress1 = '0x0200E9994260fe8D40107E01101F807B2e7A29Da';
const testKey2 =
  '0x483b7a9b979289a227095c22229028a5debe04d6d1c8434d8bd5b48f78544263'; // ! NEVER USE THIS PRIVATE KEY

vi.mock('@/hooks', () => ({
  useGenlayer: vi.fn(),
  useShortAddress: vi.fn(() => ({
    shorten: vi.fn(),
  })),
}));

vi.mock('genlayer-js', () => ({
  createAccount: vi.fn(() => ({ address: testAddress1 })),
  generatePrivateKey: vi.fn(() => testKey1),
}));

describe('useAccountsStore', () => {
  let accountsStore: ReturnType<typeof useAccountsStore>;
  const mockGenlayerClient = {
    getTransaction: vi.fn(),
  };

  beforeEach(() => {
    setActivePinia(createPinia());
    (useGenlayer as Mock).mockReturnValue({
      client: mockGenlayerClient,
    });

    // Mock localStorage
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });

    accountsStore = useAccountsStore();

    mockGenlayerClient.getTransaction.mockClear();
    (localStorage.getItem as Mock).mockClear();
    (localStorage.getItem as Mock).mockClear();
    (localStorage.removeItem as Mock).mockClear();
  });

  it('should generate a new account', () => {
    const newPrivateKey = testKey1;
    const generatedKey = accountsStore.generateNewAccount();

    expect(generatedKey).toBe(newPrivateKey);
    expect(accountsStore.privateKeys).toContain(newPrivateKey);
    expect(accountsStore.currentPrivateKey).toBe(newPrivateKey);
  });

  it('should remove an account and default to existing one', () => {
    accountsStore.privateKeys = [testKey1, testKey2];
    accountsStore.currentPrivateKey = testKey1;

    accountsStore.removeAccount(testKey1);

    expect(accountsStore.privateKeys).toEqual([testKey2]);
    expect(accountsStore.currentPrivateKey).toBe(testKey2);
  });

  it('should throw error when removing the last account', () => {
    accountsStore.privateKeys = [testKey1];

    expect(() => accountsStore.removeAccount(testKey1)).toThrow(
      'You need at least 1 account',
    );
  });

  it('should handle errors in displayAddress computation', () => {
    accountsStore.currentPrivateKey = '0xinvalidkey';

    (createAccount as Mock).mockImplementation(() => {
      throw new Error('Invalid private key');
    });

    const consoleSpy = vi.spyOn(console, 'error');
    consoleSpy.mockImplementation(() => {});

    expect(accountsStore.displayAddress).toBe('0x');

    consoleSpy.mockRestore();
    (createAccount as Mock).mockRestore();
  });

  it('should set current account', () => {
    const newPrivateKey = testKey2;
    accountsStore.setCurrentAccount(newPrivateKey);

    expect(accountsStore.currentPrivateKey).toBe(newPrivateKey);
  });

  it('should compute currentUserAddress correctly', () => {
    const privateKey = testKey1;
    const account = { address: testAddress1 };
    accountsStore.currentPrivateKey = privateKey;

    expect(accountsStore.currentUserAddress).toBe(testAddress1);
    expect(createAccount).toHaveBeenCalledWith(privateKey);
  });

  it('should return an empty string for currentUserAddress when no private key is set', () => {
    accountsStore.currentPrivateKey = null;
    expect(accountsStore.currentUserAddress).toBe('');
  });
});
