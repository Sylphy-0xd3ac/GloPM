// src/middlewares/auth.ts
import { Context, Next } from 'koa';
import { Db, ObjectId } from 'mongodb';

export function authenticate(db: Db) {
  return async (ctx: Context, next: Next) => {
    // 建议使用 ctx.get 获取请求头
    const apiKey = ctx.get('x-api-key');
    const userId = ctx.get('x-user-id');

    if (!apiKey) {
      ctx.status = 401;
      ctx.body = { error: '缺少 API Key' };
      return;
    }

    if (!userId) {
      ctx.status = 401;
      ctx.body = { error: '缺少 User ID' };
      return;
    }

    const user = await db.collection('users').findOne({ _id: new ObjectId(userId) });
    if (!user) {
      ctx.status = 401;
      ctx.body = { error: '无效的 User' };
      return;
    }

    if (user.apiKey !== apiKey) {
      ctx.status = 401;
      ctx.body = { error: '错误的 API Key' };
      return;
    }

    // 将 userId 挂载到 ctx.state 上，以便后续使用
    ctx.state.userId = userId;
    await next();
  };
}