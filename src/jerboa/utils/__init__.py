class KeyWrapper:

  def __init__(self, iterable, key):
    self.it = iterable
    self.key = key

  def __getitem__(self, i):
    return self.key(self.it[i])

  def __len__(self):
    return len(self.it)
