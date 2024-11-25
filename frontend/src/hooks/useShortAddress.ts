export const useShortAddress = () => {
  function shorten(address?: string) {
    if (!address) {
      return '';
    }

    const maxChars = 4;
    const displayedChars = Math.min(Math.floor(address.length / 3), maxChars);

    return (
      address.slice(0, displayedChars) + '...' + address.slice(-displayedChars)
    );
  }

  return {
    shorten,
  };
};
