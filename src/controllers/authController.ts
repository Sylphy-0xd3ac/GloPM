// src/controllers/authController.ts
import { Context } from 'koa';
import { Db, ObjectId } from 'mongodb';
import bcrypt from 'bcrypt';
import crypto from 'node:crypto';
/**
 * 生成统一 API Key 的示例方法
 */
export function generateApiKey(): string {
    return crypto.randomBytes(32).toString('hex');
}

export class AuthController {
  private db: Db;

  constructor(db: Db) {
    this.db = db;
  }

  /**
   * 用户注册
   * POST /api/auth/register
   * body: { username, password }
   */
  async register(ctx: Context) {
    try {
      const { username, password } = ctx.request.body as {
        username: string;
        password: string;
      };

      // 检查用户名或邮箱是否已存在
      const existingUser = await this.db.collection('users').findOne({
        $or: [{ username }]
      });
      if (existingUser) {
        ctx.status = 400;
        ctx.body = { error: '用户名已存在' };
        return;
      }

      // 生成密码哈希和 API Key
      const passwordHash = await bcrypt.hash(password, 10);
      const apiKey = generateApiKey();

      // 写入数据库
      const result = await this.db.collection('users').insertOne({
        username,
        password: passwordHash,
        apiKey,
        createdAt: new Date(),
        lastLogin: new Date()
      });

      ctx.status = 201;
      ctx.body = {
        apiKey,
        userId: result.insertedId
      };
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }

  /**
   * 用户登录（示例实现）
   * POST /api/auth/login
   * body: { username, password }
   */
  async login(ctx: Context) {
    try {
      const { username, password } = ctx.request.body as {
        username: string;
        password: string;
      };

      const user = await this.db.collection('users').findOne({ username });
      if (!user) {
        ctx.status = 401;
        ctx.body = { error: '用户不存在' };
        return;
      }

      const validPassword = await bcrypt.compare(password, user.password);
      if (!validPassword) {
        ctx.status = 401;
        ctx.body = { error: '密码错误' };
        return;
      }

      // 更新最后登录时间
      await this.db.collection('users').updateOne(
        { _id: user._id },
        { $set: { lastLogin: new Date() } }
      );

      ctx.body = { message: '登录成功', userId: user._id, apiKey: user.apiKey };
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }

  /**
   * 删除账号（示例实现）
   * DELETE /api/auth/
   * header: x-api-key, x-user-id
   */
  async removeAccount(ctx: Context) {
    try {
      // 认证中间件已将 userId 保存在 ctx.state.userId 上
      const userId = ctx.state.userId as string;
      if (!userId) {
        ctx.status = 401;
        ctx.body = { error: '未认证' };
        return;
      }
      // 删除用户
      await this.db.collection('users').deleteOne({ _id: new ObjectId(userId) });
      // 删除用户创建的包
      await this.db.collection('packages').deleteMany({ owner: new ObjectId(userId) });
      ctx.body = { message: '账号已删除' };
    } catch (error: any) {
      ctx.status = 500;
      ctx.body = { error: error.message };
    }
  }
}
