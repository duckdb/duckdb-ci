namespace duckdb {

class DBConfig;

class ExtensionHelper {
public:
	static void RegisterLinkedExtensions(DBConfig &config);
};

void ExtensionHelper::RegisterLinkedExtensions(DBConfig &) {
}

} // namespace duckdb
