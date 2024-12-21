// global.d.ts
interface Window {
    ethereum?: {
        isMetaMask?: boolean;
        request: (args: { method: string; params?: unknown[] }) => Promise<Array>;
        on: (method: string, callback: Function) => {

        }
    }
}
