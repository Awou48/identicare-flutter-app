sealed class ApiResult<T> {
  const ApiResult();

  bool get isOk => this is Ok<T>;

  T? get valueOrNull => switch (this) {
        Ok<T>(value: final v) => v,
        ApiFailure<T>() => null,
      };

  R when<R>({
    required R Function(T value) ok,
    required R Function(ApiFailure<T> failure) failure,
  }) {
    return switch (this) {
      Ok<T>(value: final v) => ok(v),
      ApiFailure<T> f => failure(f),
    };
  }
}

class Ok<T> extends ApiResult<T> {
  final T value;
  const Ok(this.value);
}

class ApiFailure<T> extends ApiResult<T> {
  final String errorCode;

  final String message;

  final int? statusCode;
  final String? requestId;
  final Map<String, dynamic> details;

  const ApiFailure({
    required this.errorCode,
    required this.message,
    this.statusCode,
    this.requestId,
    this.details = const {},
  });

  bool get isNetworkError => errorCode == 'NETWORK_ERROR';

  bool get isSessionGone =>
      errorCode == 'SESSION_EXPIRED' ||
      errorCode == 'SESSION_NOT_FOUND' ||
      errorCode == 'SESSION_CLOSED';

  @override
  String toString() => 'ApiFailure($errorCode: $message)';
}
